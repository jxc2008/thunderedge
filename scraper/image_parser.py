# scraper/image_parser.py
"""
Parse PrizePicks line cards from screenshot images using OCR.
Extracts player names and kill lines from the card layout.

Improvements:
- Image preprocessing for better OCR accuracy
- Multi-engine support (pytesseract + easyocr)
- Confidence filtering
- Batch processing support
- Team name blacklist to avoid misidentifying team names as IGNs
"""
import re
import logging
from typing import Dict, List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    from config import Config
    _STATIC_BLACKLIST = Config.OCR_TEAM_BLACKLIST
except ImportError:
    _STATIC_BLACKLIST = frozenset()

_VLR_TEAM_CACHE = None


def _get_team_blacklist() -> frozenset:
    """Combine static config blacklist with VLR-scraped teams from 2026 Kickoff."""
    global _VLR_TEAM_CACHE
    if _VLR_TEAM_CACHE is not None:
        return _VLR_TEAM_CACHE
    base = set(_STATIC_BLACKLIST)
    try:
        from scraper.vlr_scraper import VLRScraper
        vlr_teams = VLRScraper.get_teams_from_vct_events()
        base.update(vlr_teams)
        logger.info(f"OCR blacklist: {len(_STATIC_BLACKLIST)} static + {len(vlr_teams)} from VLR = {len(base)} fragments")
    except Exception as e:
        logger.warning(f"Could not fetch VLR teams for OCR blacklist: {e}. Using static list only.")
    _VLR_TEAM_CACHE = frozenset(base)
    return _VLR_TEAM_CACHE


# For backward compat; actual blacklist is built lazily via _get_team_blacklist()
TEAM_BLACKLIST = _STATIC_BLACKLIST


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
    """
    Player IGNs: SINGLE WORD names like 'Rb', 'TenZ', 'aspas', 'Monyet', 'Jemkin'
    
    Key insight: IGNs are ALWAYS one word. Team names are multiple words.
    - IGN: "Rb", "Monyet", "aspas"
    - Team: "Rex Regum Qeon", "Nongshim RedForce", "Gentle Mates"
    """
    t = str(text).strip()
    
    # IGNs are single words - this is the most important filter
    words = t.split()
    if len(words) != 1:
        return False  # Team names have spaces, IGNs don't
    
    # Length check - IGNs are typically 2-15 characters (single word)
    if len(t) < 2 or len(t) > 15:
        return False
    
    # Skip purely numeric strings
    if re.match(r'^[\d\.\-:]+$', t):
        return False
    
    # Skip team names and UI labels (static + VLR-scraped from 2026 Kickoff)
    if t.lower() in _get_team_blacklist():
        return False
    
    # Skip strings with time patterns "1:00AM"
    if re.search(r'\d+:\d+', t):
        return False
    
    # Skip strings with "MAPS" or "KILL"
    if 'MAP' in t.upper() or 'KILL' in t.upper():
        return False
    
    # Skip engagement/stats numbers "1.0K", "98.6%"
    if re.match(r'^\d+\.\d+[Kk%]?$', t):
        return False
    
    # Skip strings that are mostly punctuation or special chars
    if re.match(r'^[\W_]+$', t):
        return False
    
    # If it's a single word, alphanumeric, reasonable length -> likely an IGN
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
    
    # PSM 11: Sparse text. Find as much text as possible in no particular order.
    # Better for card-based layouts like PrizePicks
    config = '--psm 11 --oem 3'  # Sparse text + LSTM OCR Engine
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=config)
    
    detections = []
    for i, text in enumerate(data['text']):
        t = str(text).strip()
        if not t:
            continue
        
        conf = int(data['conf'][i])
        
        # More lenient confidence filtering - short names like "Rb" might have lower confidence
        # but are still valid if they pass our heuristics
        if use_confidence and conf < 20:  # Lower threshold from 30 to 20
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


def _detect_combo_maps_from_detections(detections: List) -> int:
    """
    Scan OCR text for MAPS 1-2 vs MAPS 1-3 to detect Bo3 vs Bo5 combo type.
    PrizePicks cards show "MAPS 1-2 Kills" or "MAPS 1-3 Kills" below the line.
    Returns 2 for Bo3 (Maps 1+2), 3 for Bo5 (Maps 1+2+3). Default 2.
    """
    # Build combined string from ALL detection text - OCR often splits
    # "MAPS 1-3 Kills" into separate tokens: "MAPS", "1", "-", "3", "Kills"
    combined = " ".join(
        item[2] if len(item) >= 3 else str(item)
        for item in detections
    )

    # Patterns: 1-3, 1 - 3, 1–3 (en-dash), 1—3 (em-dash), 1.3 (OCR misreads - as .)
    # 1 3 when MAPS/KILLS nearby. (?!\d) avoids 1-30 or 1-25
    # maps\s*1\s*[-.\s]+\s*3 catches "MAPS 1 3" when Kills is missing or split
    pat_1_3 = re.compile(
        r'1\s*[-–—]\s*3(?!\d)|'
        r'1\s*\.\s*3(?!\d)|'
        r'1\s+3(?=.*(?:maps|kills))|'
        r'maps\s*1\s*[-–—.\s]+\s*3(?!\d)|'
        r'1\s*[-–—.]?\s*3\s*kills',
        re.IGNORECASE
    )
    pat_1_2 = re.compile(
        r'1\s*[-–—]\s*2(?!\d)|'
        r'1\s*\.\s*2(?!\d)|'
        r'1\s+2(?=.*(?:maps|kills))|'
        r'maps\s*1\s*[-–—.\s]+\s*2(?!\d)|'
        r'1\s*[-–—.]?\s*2\s*kills',
        re.IGNORECASE
    )

    # Search in combined string first (handles split tokens)
    found_1_3 = 1 if pat_1_3.search(combined) else 0
    found_1_2 = 1 if pat_1_2.search(combined) else 0

    # Also check per-token for edge cases (e.g. "1-3" as single token)
    for item in detections:
        t = (item[2] if len(item) >= 3 else str(item))
        if pat_1_3.search(t):
            found_1_3 += 1
        if pat_1_2.search(t):
            found_1_2 += 1

    if found_1_3 > 0:
        logger.debug(f"Bo5 detected: found '1-3' in OCR text (combined snippet: ...{combined[:200]})")
        return 3
    if found_1_2 > 0:
        logger.debug(f"Bo3 detected: found '1-2' in OCR text")
        return 2
    logger.debug(f"No MAPS 1-2/1-3 found in OCR. Combined text snippet: ...{combined[:300]}")
    return 2  # default Bo3


def parse_prizepicks_image(image_bytes: bytes, use_preprocessing=True, multi_engine=False) -> tuple:
    """
    Parse PrizePicks screenshot to extract player names and kill lines.
    Detects MAPS 1-2 (Bo3) vs MAPS 1-3 (Bo5) from card text.
    
    Args:
        image_bytes: Screenshot image bytes
        use_preprocessing: Apply image enhancement before OCR (recommended)
        multi_engine: Try both pytesseract AND easyocr for better accuracy (slower)
    
    Returns:
        (projections: List[{"player_name": str, "line": float}], combo_maps: int)
    """
    import io
    from PIL import Image
    
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    original_img = img.copy()
    
    # Preprocess image for better OCR
    # Try gentle preprocessing first - aggressive can sometimes blur text
    if use_preprocessing:
        try:
            img = _preprocess_image(img, aggressive=False)
            logger.info("Applied image preprocessing (gentle mode)")
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
    all_text = []  # For debugging
    
    for item in detections:
        cx, cy, t = item if len(item) == 3 else (item[0], item[1], item[2])
        all_text.append((cx, cy, t))
        
        if _is_likely_line_value(t):
            try:
                line_values.append((cx, cy, float(t)))
                logger.debug(f"Line value detected: {t} at ({cx}, {cy})")
            except ValueError:
                pass
        
        if _is_likely_player_name(t):
            player_names.append((cx, cy, t))
            logger.debug(f"Player name candidate: '{t}' at ({cx}, {cy})")

    logger.info(f"Found {len(line_values)} line values and {len(player_names)} player name candidates")

    # For each line value, find nearest player name above it (within same card ~ same x)
    # PrizePicks layout: Team -> IGN -> Match -> Line -> "MAPS 1-2 Kills"
    HORIZ_THRESHOLD = 200  # max horizontal distance (same card)
    MIN_VERT_DISTANCE = 20  # player should be at least 20px above line
    MAX_VERT_DISTANCE = 250  # but not more than 250px above
    parsed = []
    used_players = set()

    for lx, ly, line_val in sorted(line_values, key=lambda x: (x[1], x[0])):
        # Find candidates above this line
        candidates = []
        for px, py, pname in player_names:
            if pname in used_players:
                continue
            
            # Must be above the line
            if py >= ly:
                continue
            
            # Check horizontal alignment (same card)
            dx = abs(px - lx)
            if dx > HORIZ_THRESHOLD:
                continue
            
            # Check vertical distance
            dy = ly - py
            if dy < MIN_VERT_DISTANCE or dy > MAX_VERT_DISTANCE:
                continue  # Too close or too far vertically
            
            # Calculate score: prefer closer + shorter names (IGNs are typically 1 word)
            # IGNs: "Rb", "aspas", "TenZ" vs Teams: "Nongshim RedForce"
            word_count = len(pname.split())
            name_length_penalty = len(pname) if word_count > 1 else 0
            
            # Distance score (lower is better)
            dist = dy + (dx * 0.5) + (name_length_penalty * 2)
            candidates.append((dist, pname, px, py))
        
        # Choose the best candidate (shortest distance, prefer short names)
        if candidates:
            candidates.sort(key=lambda x: x[0])  # Sort by score
            best_dist, best_player, best_px, best_py = candidates[0]
            
            logger.debug(f"Line {line_val} at ({lx},{ly}) matched to '{best_player}' at ({best_px},{best_py})")
            used_players.add(best_player)
            parsed.append({"player_name": best_player, "line": line_val})
        else:
            logger.warning(f"No player found for line {line_val} at ({lx},{ly})")
            # Still add it so we know how many lines were detected
            parsed.append({"player_name": f"Unknown_{line_val}", "line": line_val})

    # Dedupe by (player, line)
    seen = set()
    unique = []
    for p in parsed:
        k = (p["player_name"], p["line"])
        if k not in seen:
            seen.add(k)
            unique.append(p)

    # Detect MAPS 1-2 vs MAPS 1-3 from OCR text
    combo_maps = _detect_combo_maps_from_detections(detections)
    logger.info(f"Parsed {len(unique)} lines from image; detected combo: Maps 1+2 (Bo3)" if combo_maps == 2 else f"Parsed {len(unique)} lines from image; detected combo: Maps 1+2+3 (Bo5)")

    return unique, combo_maps


def parse_prizepicks_images_batch(image_bytes_list: List[bytes], 
                                   use_preprocessing=True, 
                                   multi_engine=False) -> tuple:
    """
    Parse multiple PrizePicks screenshots and combine results.
    Automatically deduplicates across all images.
    
    Returns:
        (projections: List[{"player_name": str, "line": float}], combo_maps: int)
        combo_maps uses most common detected value across images, default 2.
    """
    all_projections = []
    combo_counts = {2: 0, 3: 0}
    
    for i, image_bytes in enumerate(image_bytes_list):
        try:
            projections, combo_maps = parse_prizepicks_image(image_bytes, use_preprocessing, multi_engine)
            all_projections.extend(projections)
            combo_counts[combo_maps] = combo_counts.get(combo_maps, 0) + 1
            logger.info(f"Image {i+1}/{len(image_bytes_list)}: Parsed {len(projections)} lines, combo={combo_maps}")
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
    
    # Use most common combo_maps across images
    combo_maps = 3 if combo_counts.get(3, 0) > combo_counts.get(2, 0) else 2
    logger.info(f"Batch total: {len(all_projections)} parsed, {len(unique)} unique lines; combo_maps={combo_maps}")
    return unique, combo_maps
