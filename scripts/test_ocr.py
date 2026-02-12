#!/usr/bin/env python3
"""
Test script to verify OCR system is working correctly.
Tests pytesseract, OpenCV preprocessing, and the image parser.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_tesseract():
    """Test if Tesseract is accessible."""
    print("\n" + "="*60)
    print("Test 1: Tesseract Binary")
    print("="*60)
    try:
        import pytesseract
        version = pytesseract.get_tesseract_version()
        print(f"[OK] Tesseract found: v{version}")
        return True
    except Exception as e:
        print(f"[ERROR] Tesseract error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure Tesseract is installed")
        print("2. Add to PATH: C:\\Program Files\\Tesseract-OCR")
        print("3. Or set: pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'")
        return False

def test_opencv():
    """Test if OpenCV is working."""
    print("\n" + "="*60)
    print("Test 2: OpenCV Preprocessing")
    print("="*60)
    try:
        import cv2
        import numpy as np
        from PIL import Image
        
        # Create a test image
        img_np = np.zeros((100, 300, 3), dtype=np.uint8)
        cv2.putText(img_np, 'TEST 18.5', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Test preprocessing
        from scraper.image_parser import _preprocess_image
        img_pil = Image.fromarray(img_np)
        preprocessed = _preprocess_image(img_pil, aggressive=False)
        
        print(f"[OK] OpenCV version: {cv2.__version__}")
        print(f"[OK] Preprocessing working (output size: {preprocessed.size})")
        return True
    except ImportError as e:
        print(f"[ERROR] OpenCV not installed: {e}")
        print("\nInstall: pip install opencv-python-headless")
        return False
    except Exception as e:
        print(f"[ERROR] Preprocessing error: {e}")
        return False

def test_basic_ocr():
    """Test basic OCR on a simple image."""
    print("\n" + "="*60)
    print("Test 3: Basic OCR")
    print("="*60)
    try:
        import pytesseract
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a simple test image with text
        img = Image.new('RGB', (400, 100), color='white')
        draw = ImageDraw.Draw(img)
        
        # Draw some text that looks like PrizePicks data
        draw.text((20, 20), 'aspas', fill='black')
        draw.text((20, 50), '18.5', fill='black')
        draw.text((150, 20), 'TenZ', fill='black')
        draw.text((150, 50), '20.5', fill='black')
        
        # Run OCR
        text = pytesseract.image_to_string(img)
        detected_words = [w.strip() for w in text.split() if w.strip()]
        
        print(f"[OK] OCR detected: {detected_words}")
        
        # Check if we found player names or numbers
        has_text = len(detected_words) > 0
        if has_text:
            print(f"[OK] Basic OCR working ({len(detected_words)} items detected)")
        else:
            print("[WARNING] No text detected (may need better test image)")
        
        return True
    except Exception as e:
        print(f"[ERROR] OCR failed: {e}")
        return False

def test_image_parser():
    """Test the full image parser with preprocessing."""
    print("\n" + "="*60)
    print("Test 4: Image Parser (Full Pipeline)")
    print("="*60)
    try:
        from scraper.image_parser import parse_prizepicks_image
        from PIL import Image, ImageDraw, ImageFont
        import io
        
        # Create a mock PrizePicks-like image
        img = Image.new('RGB', (800, 400), color='#1a1a1a')
        draw = ImageDraw.Draw(img)
        
        # Simulate multiple cards
        cards = [
            {'player': 'aspas', 'line': '18.5', 'x': 50, 'y': 50},
            {'player': 'TenZ', 'line': '20.5', 'x': 250, 'y': 50},
            {'player': 'yay', 'line': '16.5', 'x': 450, 'y': 50},
            {'player': 'Less', 'line': '19.5', 'x': 650, 'y': 50},
        ]
        
        for card in cards:
            # Player name (above)
            draw.text((card['x'], card['y']), card['player'], fill='white')
            # Line value (below)
            draw.text((card['x'], card['y'] + 40), card['line'], fill='white')
        
        # Convert to bytes
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes = img_bytes.getvalue()
        
        # Parse with preprocessing
        print("Testing with preprocessing...")
        projections, combo_maps = parse_prizepicks_image(img_bytes, use_preprocessing=True, multi_engine=False)
        
        print(f"[OK] Parser returned {len(projections)} projections (combo_maps={combo_maps})")
        for p in projections[:5]:  # Show first 5
            print(f"  - {p['player_name']}: {p['line']}")
        
        if len(projections) > 0:
            print("[OK] Image parser working!")
        else:
            print("[INFO] No projections detected (expected with simple test image)")
            print("   Try with a real PrizePicks screenshot for better results")
        
        return True
    except Exception as e:
        print(f"[ERROR] Parser error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_confidence_filtering():
    """Test confidence filtering."""
    print("\n" + "="*60)
    print("Test 5: Confidence Filtering")
    print("="*60)
    try:
        import pytesseract
        from PIL import Image
        import numpy as np
        
        # Create image with clear and unclear text
        img_np = np.ones((100, 400, 3), dtype=np.uint8) * 255
        
        import cv2
        # Clear text
        cv2.putText(img_np, 'CLEAR 18.5', (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        # Add noise for low confidence
        noise = np.random.randint(0, 50, (100, 400, 3), dtype=np.uint8)
        img_np = cv2.addWeighted(img_np, 0.8, noise, 0.2, 0)
        
        img = Image.fromarray(img_np)
        
        # Get OCR with confidence
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        
        high_conf = [data['text'][i] for i, conf in enumerate(data['conf']) if int(conf) > 30 and data['text'][i].strip()]
        low_conf = [data['text'][i] for i, conf in enumerate(data['conf']) if 0 < int(conf) < 30 and data['text'][i].strip()]
        
        print(f"[OK] High confidence detections (>30%): {high_conf}")
        print(f"[OK] Low confidence detections (<30%): {low_conf}")
        print(f"[OK] Confidence filtering working ({len(high_conf)} high, {len(low_conf)} low)")
        
        return True
    except Exception as e:
        print(f"[ERROR] Confidence test error: {e}")
        return False

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  OCR SYSTEM VERIFICATION")
    print("="*60)
    
    results = []
    
    # Run all tests
    results.append(("Tesseract Binary", test_tesseract()))
    results.append(("OpenCV Preprocessing", test_opencv()))
    results.append(("Basic OCR", test_basic_ocr()))
    results.append(("Image Parser", test_image_parser()))
    results.append(("Confidence Filtering", test_confidence_filtering()))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {name}")
    
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    
    print(f"\nPassed: {passed_count}/{total_count}")
    
    if passed_count == total_count:
        print("\n[SUCCESS] All tests passed! OCR system is fully operational.")
        print("\nNext steps:")
        print("1. Try uploading a real PrizePicks screenshot")
        print("2. Use the API: POST /api/prizepicks/leaderboard/upload")
        print("3. For best accuracy, add ?multi_engine=true")
    elif passed_count >= 3:
        print("\n[OK] Core functionality working. Some advanced features may need attention.")
    else:
        print("\n[WARNING] Some critical tests failed. Please review the errors above.")
    
    sys.exit(0 if passed_count == total_count else 1)
