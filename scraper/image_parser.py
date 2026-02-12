# scraper/image_parser.py
"""
Parse PrizePicks line cards from screenshot images using OCR.
Extracts player names and kill lines from the card layout.
"""
import re
import logging
from typing import Dict, List, Tuple

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


def _ocr_with_pytesseract(img) -> List[Tuple[float, float, str]]:
    """Use pytesseract (lighter, requires Tesseract binary). Returns [(cx, cy, text), ...]"""
    import pytesseract
    from PIL import Image
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    detections = []
    for i, text in enumerate(data['text']):
        t = str(text).strip()
        if not t:
            continue
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        cx, cy = x + w / 2, y + h / 2
        detections.append((cx, cy, t))
    return detections


def _ocr_with_easyocr(img_np) -> List[Tuple[float, float, str]]:
    """Use easyocr (heavier, needs torch). Returns [(cx, cy, text), ...]"""
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False)
    results = reader.readtext(img_np)
    out = []
    for (bbox, text, _) in results:
        cx, cy = _bbox_center(bbox)
        out.append((cx, cy, str(text).strip()))
    return out


def parse_prizepicks_image(image_bytes: bytes) -> List[Dict]:
    """
    Parse PrizePicks screenshot to extract player names and MAPS 1-2 Kills lines.
    Card layout: team -> player name -> match -> LINE -> MAPS 1-2 Kills
    
    Tries pytesseract first (lighter). Falls back to easyocr if available.
    Returns list of {"player_name": str, "line": float} dicts.
    """
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')

    detections = []
    try:
        import pytesseract
        detections = _ocr_with_pytesseract(img)
    except Exception as e1:
        logger.info(f"pytesseract unavailable: {e1}")
        try:
            import numpy as np
            detections = _ocr_with_easyocr(np.array(img))
        except ImportError:
            raise ImportError(
                "OCR required. Install either:\n"
                "  • pytesseract + Tesseract: pip install pytesseract, then install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki\n"
                "  • easyocr: pip install easyocr (larger install, ~2GB)"
            )

    line_values = [(cx, cy, float(t)) for (cx, cy, t) in detections if _is_likely_line_value(t)]
    player_names = [(cx, cy, t) for (cx, cy, t) in detections if _is_likely_player_name(t)]

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
