# scraper/image_parser.py
"""
Parse PrizePicks line cards from screenshot images using OCR.
Extracts player names and kill lines from the card layout.

Improvements:
- Image preprocessing for better OCR accuracy
- Multi-engine support (pytesseract + easyocr)
- Confidence filtering
- Batch processing support
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


def _bbox_center(bbox) -> Tuple[float, float]:
    """ (x_center, y_center) from bbox [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] """
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _is_likely_line_value(text: str) -> bool:
    """ Line values are typically 15-50, can have .5 """
    text = str(text).strip()
    if not text:
        return False
    try:
        v = float(text)
        return 12 <= v <= 55
    except ValueError:
        return False


def _is_likely_player_name(text: str) -> bool:
    """ Player names: short alphanumeric, possibly with numbers/underscores """
    t = str(text).strip()
    if len(t) < 2 or len(t) > 25:
        return False
    if re.match(r'^[\d\s\.\-:]+$', t):  # mostly numbers
        return False
    # Skip team/label words - NOT "loss" (Loss is a player on FURIA Academy)
    skip = ('maps', 'kills', 'less', 'more', 'vs', 'at', 'thu', 'fri', 'sat', 'sun',
            'am', 'pm', 'g', 'academy', 'canids', 'liquid', 'heretics', 'rex', 'paper', 'furia', 'red',
            'drx', 'val', 'tl', 'vct', 'valorant')
    if t.lower() in skip:
        return False
    if 'MAPS' in t.upper() or 'KILL' in t.upper():
        return False
    if re.match(r'^\d+\.\d+[Kk]?$', t):  # engagement numbers like 1.0K
        return False
    return True


def _preprocess_image(img, aggressive=False):
    """
    Enhance image for better OCR accuracy.
    
    Args:
        img: PIL Image
        aggressive: If True, applies stronger preprocessing (may help with poor quality images)
    
    Returns:
        Preprocessed PIL Image
    """
    try:
        import cv2
    except ImportError:
        logger.warning("opencv-python not installed, skipping preprocessing")
        return img
    
    img_np = np.array(img)
    
    # Convert to grayscale
    if len(img_np.shape) == 3:
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_np
    
    if aggressive:
        # Stronger preprocessing for difficult images
        # 1. Increase contrast significantly
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # 2. Denoise aggressively
        denoised = cv2.fastNlMeansDenoising(enhanced, h=10)
        
        # 3. Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        
        # 4. Upscale for small text
        upscaled = cv2.resize(thresh, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        from PIL import Image
        return Image.fromarray(upscaled)
    else:
        # Gentle preprocessing (default)
        # 1. Moderate contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # 2. Light denoising
        denoised = cv2.fastNlMeansDenoising(enhanced, h=5)
        
        # 3. Slight upscale
        upscaled = cv2.resize(denoised, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
        
        from PIL import Image
        return Image.fromarray(upscaled)


def _ocr_with_pytesseract(img, use_confidence=True) -> List[Tuple[float, float, str, Optional[int]]]:
    """
    Use pytesseract (lighter, requires Tesseract binary). 
    Returns [(cx, cy, text, confidence), ...]
    """
    import pytesseract
    from PIL import Image
    
    config = '--psm 6'  # Assume uniform block of text
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=config)
    
    detections = []
    for i, text in enumerate(data['text']):
        t = str(text).strip()
        if not t:
            continue
        
        conf = int(data['conf'][i])
        
        # Filter low confidence detections
        if use_confidence and conf < 30:
            continue
        
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        cx, cy = x + w / 2, y + h / 2
        detections.append((cx, cy, t, conf))
    
    return detections


def _ocr_with_easyocr(img_np, use_confidence=True) -> List[Tuple[float, float, str, Optional[float]]]:
    """
    Use easyocr (heavier, needs torch). 
    Returns [(cx, cy, text, confidence), ...]
    """
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    results = reader.readtext(img_np)
    
    out = []
    for (bbox, text, conf) in results:
        # Filter low confidence
        if use_confidence and conf < 0.3:  # easyocr confidence is 0-1
            continue
        
        cx, cy = _bbox_center(bbox)
        out.append((cx, cy, str(text).strip(), conf))
    
    return out


def _merge_detections(detections_pytess, detections_easy):
    """
    Merge detections from multiple OCR engines.
    Combines results, deduplicates nearby detections, prefers higher confidence.
    """
    if not detections_easy:
        return detections_pytess
    if not detections_pytess:
        return detections_easy
    
    # Convert to common format
    all_detections = []
    for cx, cy, text, conf in detections_pytess:
        all_detections.append((cx, cy, text, conf or 50, 'pytess'))
    for cx, cy, text, conf in detections_easy:
        all_detections.append((cx, cy, text, int(conf * 100) if conf else 50, 'easy'))
    
    # Group nearby detections (within 20 pixels)
    merged = []
    used = set()
    
    for i, (cx1, cy1, text1, conf1, src1) in enumerate(all_detections):
        if i in used:
            continue
        
        # Find nearby duplicates
        group = [(cx1, cy1, text1, conf1, src1)]
        for j, (cx2, cy2, text2, conf2, src2) in enumerate(all_detections[i+1:], start=i+1):
            if j in used:
                continue
            
            # Check if positions are close
            dist = ((cx1 - cx2)**2 + (cy1 - cy2)**2)**0.5
            if dist < 20:  # Same detection
                group.append((cx2, cy2, text2, conf2, src2))
                used.add(j)
        
        # Choose best from group (highest confidence)
        best = max(group, key=lambda x: x[3])
        merged.append((best[0], best[1], best[2], best[3]))
        used.add(i)
    
    return merged


def parse_prizepicks_image(image_bytes: bytes, use_preprocessing=True, multi_engine=False) -> List[Dict]:
    """
    Parse PrizePicks screenshot to extract player names and MAPS 1-2 Kills lines.
    Card layout: team -> player name -> match -> LINE -> MAPS 1-2 Kills
    
    Args:
        image_bytes: Screenshot image bytes
        use_preprocessing: Apply image enhancement before OCR (recommended)
        multi_engine: Try both pytesseract AND easyocr for better accuracy (slower)
    
    Returns:
        List of {"player_name": str, "line": float} dicts
    """
    import io
    from PIL import Image
    
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    original_img = img.copy()
    
    # Preprocess image for better OCR
    if use_preprocessing:
        try:
            img = _preprocess_image(img, aggressive=False)
            logger.info("Applied image preprocessing")
        except Exception as e:
            logger.warning(f"Preprocessing failed, using original: {e}")
            img = original_img

    detections = []
    detections_pytess = []
    detections_easy = []
    
    # Try pytesseract
    try:
        import pytesseract
        detections_pytess = _ocr_with_pytesseract(img, use_confidence=True)
        logger.info(f"pytesseract detected {len(detections_pytess)} items")
    except Exception as e1:
        logger.info(f"pytesseract unavailable: {e1}")
    
    # Try easyocr if multi_engine or if pytesseract failed
    if multi_engine or not detections_pytess:
        try:
            import numpy as np
            img_np = np.array(img)
            detections_easy = _ocr_with_easyocr(img_np, use_confidence=True)
            logger.info(f"easyocr detected {len(detections_easy)} items")
        except Exception as e2:
            logger.info(f"easyocr unavailable: {e2}")
    
    # Merge results if using both engines
    if multi_engine and detections_pytess and detections_easy:
        detections = _merge_detections(detections_pytess, detections_easy)
        logger.info(f"Merged to {len(detections)} unique detections")
    elif detections_pytess:
        detections = [(cx, cy, t) for cx, cy, t, _ in detections_pytess]
    elif detections_easy:
        detections = [(cx, cy, t) for cx, cy, t, _ in detections_easy]
    else:
        raise ImportError(
            "OCR required. Install either:\n"
            "  • pytesseract + Tesseract: pip install pytesseract, then install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  • easyocr: pip install easyocr (larger install, ~2GB)\n"
            "  • opencv-python: pip install opencv-python-headless (for preprocessing)"
        )

    # Extract line values and player names
    line_values = []
    player_names = []
    
    for item in detections:
        cx, cy, t = item if len(item) == 3 else (item[0], item[1], item[2])
        
        if _is_likely_line_value(t):
            try:
                line_values.append((cx, cy, float(t)))
            except ValueError:
                pass
        
        if _is_likely_player_name(t):
            player_names.append((cx, cy, t))

    # For each line value, find nearest player name above it (within same card ~ same x)
    HORIZ_THRESHOLD = 180  # max horizontal distance (same card) - increased for wider grids
    VERT_OVERLAP = 30  # allow slight overlap (player can be slightly below line center)
    parsed = []
    used_players = set()

    for lx, ly, line_val in sorted(line_values, key=lambda x: (x[1], x[0])):
        best_player = None
        best_dist = float('inf')
        for px, py, pname in player_names:
            if pname in used_players:
                continue
            if py >= ly + VERT_OVERLAP:  # player must be above the line (with tolerance)
                continue
            dx = abs(px - lx)
            if dx > HORIZ_THRESHOLD:
                continue
            dy = ly - py
            if dy < 0:
                dy = 0  # same row or below - prefer closer horizontal
            dist = dx * 1.5 + dy  # weight horizontal alignment, prefer players directly above
            if dist < best_dist:
                best_dist = dist
                best_player = pname

        if best_player:
            used_players.add(best_player)
            parsed.append({"player_name": best_player, "line": line_val})
        else:
            parsed.append({"player_name": f"Player_{line_val}", "line": line_val})

    # Dedupe by (player, line)
    seen = set()
    unique = []
    for p in parsed:
        k = (p["player_name"], p["line"])
        if k not in seen:
            seen.add(k)
            unique.append(p)

    logger.info(f"Parsed {len(unique)} lines from image")
    return unique


def parse_prizepicks_images_batch(image_bytes_list: List[bytes], 
                                   use_preprocessing=True, 
                                   multi_engine=False) -> List[Dict]:
    """
    Parse multiple PrizePicks screenshots and combine results.
    Automatically deduplicates across all images.
    
    Args:
        image_bytes_list: List of screenshot image bytes
        use_preprocessing: Apply image enhancement
        multi_engine: Use both OCR engines
    
    Returns:
        Combined and deduplicated list of {"player_name": str, "line": float}
    """
    all_projections = []
    
    for i, image_bytes in enumerate(image_bytes_list):
        try:
            projections = parse_prizepicks_image(image_bytes, use_preprocessing, multi_engine)
            all_projections.extend(projections)
            logger.info(f"Image {i+1}/{len(image_bytes_list)}: Parsed {len(projections)} lines")
        except Exception as e:
            logger.error(f"Failed to parse image {i+1}: {e}")
    
    # Deduplicate by (player_name, line)
    seen = set()
    unique = []
    for p in all_projections:
        k = (p["player_name"].lower(), p["line"])
        if k not in seen:
            seen.add(k)
            unique.append(p)
    
    logger.info(f"Batch total: {len(all_projections)} parsed, {len(unique)} unique lines")
    return unique
