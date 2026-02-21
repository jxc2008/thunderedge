# scraper/vision_parser.py
"""
Parse PrizePicks screenshots using Google Gemini vision API.
Uses gemini-2.0-flash-lite (free tier: 15 RPM, 1000 RPD).
Requires GOOGLE_API_KEY or GEMINI_API_KEY environment variable.
"""
import base64
import json
import logging
import re
import time
from typing import List, Tuple

logger = logging.getLogger(__name__)

PROMPT = """Extract all Valorant player kill lines from this PrizePicks screenshot.

For each line card, extract:
1. The player's IGN (in-game name) - the single word name, NOT the team name
2. The kill line number (e.g. 29.5, 30, 32.5)

Ignore: team names, match names, "MAPS 1-2 Kills" labels, dates, and UI elements.
Only extract actual player IGNs and their associated line values.

Return a JSON array only, no other text. Format:
[{"player_name": "TenZ", "line": 29.5}, {"player_name": "aspas", "line": 30.5}, ...]

If you see "MAPS 1-3" or "Maps 1+2+3" anywhere, set combo_maps to 3. Otherwise use 2.
Add "combo_maps": 2 or 3 as the last object in the array, e.g. {"combo_maps": 2}.

Return ONLY valid JSON."""


def _detect_mime_type(image_bytes: bytes) -> str:
    """Detect MIME type from image magic bytes."""
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if image_bytes[:2] == b'\xff\xd8':
        return 'image/jpeg'
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return 'image/webp'
    return 'image/png'  # default


def parse_prizepicks_image_vision(image_bytes: bytes) -> Tuple[List[dict], int]:
    """
    Parse PrizePicks screenshot using Gemini 1.5 Flash vision.
    Returns (projections: [{"player_name", "line"}], combo_maps: 2 or 3).
    """
    api_key = __import__('os').environ.get('GOOGLE_API_KEY') or __import__('os').environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ImportError(
            "Vision API requires GOOGLE_API_KEY or GEMINI_API_KEY. "
            "Get a free key at https://aistudio.google.com/apikey"
        )

    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "Install: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)
    # gemini-2.0-flash-lite deprecated for new users; use gemini-2.5-flash (current)
    model = genai.GenerativeModel('gemini-2.5-flash')

    mime = _detect_mime_type(image_bytes)
    b64 = base64.b64encode(image_bytes).decode('utf-8')

    image_part = {
        'inline_data': {'mime_type': mime, 'data': b64}
    }

    try:
        response = model.generate_content(
            [image_part, PROMPT],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
            )
        )
        text = (response.text or '').strip()
        if not text:
            logger.warning("Gemini returned empty response (image may be blocked or unreadable)")
            return [], 2
    except Exception as e:
        logger.error(f"Gemini vision API error: {e}")
        raise

    # Extract JSON from response (handle markdown code blocks)
    json_match = re.search(r'\[[\s\S]*?\]', text)
    if not json_match:
        logger.warning(f"Could not find JSON array in response: {text[:500]}")
        return [], 2

    try:
        data = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON from vision: {e}. Raw: {json_match.group()[:300]}")
        return [], 2

    combo_maps = 2
    projections = []

    for item in data:
        if isinstance(item, dict):
            if 'combo_maps' in item:
                combo_maps = int(item['combo_maps']) if item['combo_maps'] in (2, 3) else 2
            elif 'player_name' in item and 'line' in item:
                name = str(item['player_name']).strip()
                try:
                    line = float(item['line'])
                except (TypeError, ValueError):
                    continue
                if name and 12 <= line <= 55:
                    projections.append({'player_name': name, 'line': line})

    return projections, combo_maps


def parse_prizepicks_images_batch_vision(image_bytes_list: List[bytes]) -> Tuple[List[dict], int]:
    """
    Parse multiple PrizePicks screenshots with Gemini vision.
    Deduplicates by (player_name, line). Uses most common combo_maps.
    """
    all_projections = []
    combo_counts = {2: 0, 3: 0}

    for i, img_bytes in enumerate(image_bytes_list):
        if i > 0:
            time.sleep(4)  # Free tier ~15 RPM; space out requests to avoid 429
        try:
            projections, combo_maps = parse_prizepicks_image_vision(img_bytes)
            all_projections.extend(projections)
            combo_counts[combo_maps] = combo_counts.get(combo_maps, 0) + 1
            logger.info(f"Vision image {i+1}/{len(image_bytes_list)}: {len(projections)} lines, combo={combo_maps}")
        except Exception as e:
            logger.error(f"Vision failed for image {i+1}: {e}")

    # Deduplicate by (player_name, line)
    seen = set()
    unique = []
    for p in all_projections:
        k = (p['player_name'].lower(), p['line'])
        if k not in seen:
            seen.add(k)
            unique.append(p)

    combo_maps = 3 if combo_counts.get(3, 0) > combo_counts.get(2, 0) else 2
    logger.info(f"Vision batch: {len(unique)} unique lines; combo_maps={combo_maps}")
    return unique, combo_maps
