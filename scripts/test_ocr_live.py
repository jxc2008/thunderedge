"""
Quick test of improved OCR parser with the provided screenshot
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scraper.image_parser import parse_prizepicks_image
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Read the screenshot the user provided
image_path = r"C:\Users\josep\.cursor\projects\c-Users-josep-OneDrive-Desktop-Thunderedge\assets\c__Users_josep_AppData_Roaming_Cursor_User_workspaceStorage_954be277b8c2fd867e1de6e2fc20d0b5_images_image-f022ee92-6f88-4f0a-a441-5fee78182f20.png"

print("\n" + "="*70)
print("TESTING IMPROVED OCR PARSER")
print("="*70)

try:
    with open(image_path, 'rb') as f:
        image_bytes = f.read()
    
    print(f"\n[1/2] Reading screenshot: {os.path.basename(image_path)}")
    print(f"      Size: {len(image_bytes)} bytes")
    
    print(f"\n[2/2] Running OCR with improved parser...")
    print("      - Aggressive preprocessing (2x upscale, CLAHE, denoising)")
    print("      - PSM 11 (sparse text mode)")
    print("      - Lower confidence threshold (20)")
    print("      - Smart IGN detection (prefers short single words)")
    print()
    
    results, combo_maps = parse_prizepicks_image(image_bytes, use_preprocessing=True, multi_engine=False)
    
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    print(f"\nDetected combo: Maps 1+2+3 (Bo5)" if combo_maps == 3 else f"\nDetected combo: Maps 1+2 (Bo3)")
    print(f"\nParsed {len(results)} lines:")
    print()
    
    for i, proj in enumerate(results, 1):
        player = proj['player_name']
        line = proj['line']
        
        # Highlight potential issues
        if player.startswith('Unknown_'):
            status = "[WARNING]"
        elif player.startswith('Player_'):
            status = "[WARNING]"
        else:
            status = "[OK]"
        
        print(f"{i:2d}. {status} {player:20s} | Line: {line}")
    
    print("\n" + "="*70)
    print("EXPECTED PLAYERS (from user's message):")
    print("="*70)
    expected = [
        "Monyet (Rex Regum Qeon) - Line 46",
        "Jemkin (Rex Regum Qeon) - Line 53.5",
        "ivy (Nongshim RedForce) - Line 41.5",
        "Minny (Gentle Mates) - Line 48",
        "...and 16 more players (20 total)"
    ]
    for exp in expected:
        print(f"  - {exp}")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"  Detected: {len(results)}/20 lines")
    
    # Check if we got the expected players
    found_players = [p['player_name'] for p in results]
    expected_igns = ['Monyet', 'Jemkin', 'ivy', 'Minny']
    
    matched = []
    missing = []
    for ign in expected_igns:
        if ign in found_players:
            matched.append(ign)
        else:
            missing.append(ign)
    
    if matched:
        print(f"\n  [SUCCESS] Found: {', '.join(matched)}")
    if missing:
        print(f"  [MISSING] Not found: {', '.join(missing)}")
    
    print("\n" + "="*70)
    
except FileNotFoundError:
    print(f"\n[ERROR] Screenshot not found at: {image_path}")
    print("Please check the path and try again.")
except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
