# OCR System Improvement & Centralized Data Solution

## Current Issues

### 1. OCR Accuracy Problems
- **Missing lines**: Layout heuristics may fail with different card arrangements
- **Single engine**: Only tries pytesseract OR easyocr, not both
- **Weak preprocessing**: No image enhancement before OCR
- **Single screenshot**: Can't process multiple images at once

### 2. Data Centralization
- **Local only**: SQLite database isn't shared across machines
- **No sync**: Each user has separate leaderboard history
- **No backup**: Data loss if database file corrupted

---

## Solution 1: Optimized OCR System

### A. Multi-Engine OCR with Voting

Use BOTH OCR engines and combine results for better accuracy:

```python
def _ocr_multi_engine(img, img_np):
    """Run both engines and combine detections."""
    detections = []
    
    # Try pytesseract
    try:
        import pytesseract
        pytess_results = _ocr_with_pytesseract(img)
        detections.extend([(cx, cy, t, 'pytess') for cx, cy, t in pytess_results])
    except Exception as e:
        logger.warning(f"pytesseract failed: {e}")
    
    # Try easyocr
    try:
        import easyocr
        easy_results = _ocr_with_easyocr(img_np)
        detections.extend([(cx, cy, t, 'easy') for cx, cy, t in easy_results])
    except Exception as e:
        logger.warning(f"easyocr failed: {e}")
    
    # Merge nearby duplicates (same position, different text)
    return _merge_duplicate_detections(detections)
```

### B. Image Preprocessing

Add preprocessing to improve OCR accuracy:

```python
def _preprocess_image(img):
    """Enhance image for better OCR."""
    import cv2
    import numpy as np
    
    img_np = np.array(img)
    
    # Convert to grayscale
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
    
    # Increase contrast (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    
    # Denoise
    denoised = cv2.fastNlMeansDenoising(enhanced)
    
    # Adaptive threshold (helps with varying lighting)
    thresh = cv2.adaptiveThreshold(
        denoised, 255, 
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
        cv2.THRESH_BINARY, 11, 2
    )
    
    # Optional: upscale for small text
    scale = 2
    upscaled = cv2.resize(thresh, None, fx=scale, fy=scale, 
                          interpolation=cv2.INTER_CUBIC)
    
    return Image.fromarray(upscaled)
```

### C. Multiple Screenshot Support

Allow batch processing:

```python
@app.route('/api/prizepicks/leaderboard/upload-batch', methods=['POST'])
def upload_leaderboard_images():
    """
    Upload multiple PrizePicks screenshots.
    Parses all, deduplicates, and ranks combined results.
    """
    from scraper.image_parser import parse_prizepicks_images_batch
    
    if 'images' not in request.files:
        return jsonify({'error': 'No images provided'}), 400
    
    files = request.files.getlist('images')
    if not files:
        return jsonify({'error': 'No files selected'}), 400
    
    all_projections = []
    for f in files:
        try:
            image_bytes = f.read()
            projections = parse_prizepicks_image(image_bytes)
            all_projections.extend(projections)
        except Exception as e:
            logger.warning(f"Failed to parse {f.filename}: {e}")
    
    # Deduplicate by (player_name, line)
    unique_projections = _deduplicate_projections(all_projections)
    
    results, skipped = _build_leaderboard_from_projections(unique_projections)
    if results:
        db.save_leaderboard_snapshot('batch_upload', results, 
                                      parsed_count=len(unique_projections))
    
    return jsonify({
        'success': True,
        'parsed_total': len(all_projections),
        'parsed_unique': len(unique_projections),
        'ranked': len(results),
        'skipped': skipped,
        'leaderboard': results
    })
```

### D. Confidence Scoring

Add confidence scores to catch low-quality detections:

```python
def _ocr_with_confidence(img):
    """OCR with confidence filtering."""
    import pytesseract
    from PIL import Image
    
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    detections = []
    
    for i, text in enumerate(data['text']):
        conf = int(data['conf'][i])
        if conf < 30:  # Skip low confidence
            continue
        
        t = str(text).strip()
        if not t:
            continue
            
        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
        cx, cy = x + w / 2, y + h / 2
        detections.append((cx, cy, t, conf))
    
    return detections
```

---

## Solution 2: Centralized Data Storage

### Option A: Cloud Database (Recommended)

**Use Supabase (PostgreSQL) or Firebase**

**Pros:**
- Free tier available
- Real-time sync across devices
- Built-in auth
- Automatic backups
- SQL queries (Supabase) or NoSQL (Firebase)

**Implementation:**

```python
# config.py
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
USE_CLOUD_DB = os.getenv('USE_CLOUD_DB', 'false').lower() == 'true'

# backend/cloud_db.py
from supabase import create_client, Client
import os

class CloudDatabase:
    def __init__(self):
        if not config.USE_CLOUD_DB:
            return
        self.supabase: Client = create_client(
            config.SUPABASE_URL, 
            config.SUPABASE_KEY
        )
    
    def save_leaderboard_snapshot(self, source: str, results: List[Dict]) -> int:
        """Save to cloud."""
        # Insert snapshot
        snapshot = self.supabase.table('leaderboard_snapshots').insert({
            'source': source,
            'parsed_count': len(results),
            'ranked_count': len(results)
        }).execute()
        
        snapshot_id = snapshot.data[0]['id']
        
        # Insert entries
        entries = [{
            'snapshot_id': snapshot_id,
            'rank': r['rank'],
            'player_name': r['player_name'],
            'line': r['line'],
            'best_side': r['best_side'],
            'p_hit': r['p_hit'],
            # ... other fields
        } for r in results]
        
        self.supabase.table('leaderboard_entries').insert(entries).execute()
        return snapshot_id
    
    def get_leaderboard_snapshots(self, limit: int = 50) -> List[Dict]:
        """Fetch from cloud."""
        response = self.supabase.table('leaderboard_snapshots')\
            .select('*')\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        return response.data
```

**Hybrid Approach:**
```python
# backend/database.py
class Database:
    def __init__(self, db_path: str):
        self.local_db = sqlite3.connect(db_path)
        self.cloud_db = CloudDatabase() if config.USE_CLOUD_DB else None
    
    def save_leaderboard_snapshot(self, source: str, results: List[Dict]) -> int:
        # Save to local first
        local_id = self._save_local_leaderboard(source, results)
        
        # Sync to cloud if enabled
        if self.cloud_db:
            try:
                cloud_id = self.cloud_db.save_leaderboard_snapshot(source, results)
                logger.info(f"Synced to cloud: {cloud_id}")
            except Exception as e:
                logger.warning(f"Cloud sync failed: {e}")
        
        return local_id
```

### Option B: Shared File Storage (Simpler)

**Use Google Drive API or Dropbox**

Store SQLite file in cloud folder that syncs across devices.

**Pros:**
- Simple - just a file
- Works with existing SQLite code
- Automatic sync via cloud service

**Cons:**
- Slower than database
- Potential conflicts if multiple users write simultaneously
- No real-time updates

### Option C: GitHub as Database (Creative)

**Store leaderboard history as JSON files in a GitHub repo**

```python
# backend/github_db.py
import os
import json
from github import Github

class GitHubDatabase:
    def __init__(self):
        self.g = Github(os.getenv('GITHUB_TOKEN'))
        self.repo = self.g.get_repo('jxc2008/thunderedge-leaderboards')
    
    def save_leaderboard_snapshot(self, source: str, results: List[Dict]) -> str:
        """Save as JSON file in repo."""
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f"leaderboards/{timestamp}_{source}.json"
        
        content = json.dumps({
            'created_at': timestamp,
            'source': source,
            'leaderboard': results
        }, indent=2)
        
        self.repo.create_file(
            path=filename,
            message=f"Add leaderboard: {source}",
            content=content
        )
        return filename
    
    def get_leaderboard_snapshots(self, limit: int = 50) -> List[Dict]:
        """List recent leaderboards."""
        contents = self.repo.get_contents("leaderboards")
        # Sort by filename (timestamp), take last N
        files = sorted(contents, key=lambda x: x.name, reverse=True)[:limit]
        
        snapshots = []
        for f in files:
            data = json.loads(f.decoded_content)
            snapshots.append(data)
        return snapshots
```

**Pros:**
- Free
- Version control for free
- Easy to share/view on GitHub
- Can create PRs for review

**Cons:**
- Slower than real database
- Not designed for this use case
- Rate limited

---

## Recommended Solution

### Phase 1: Optimize OCR (Immediate)
1. ✅ Add image preprocessing
2. ✅ Use multi-engine voting
3. ✅ Add confidence filtering
4. ✅ Support multiple screenshots

### Phase 2: Cloud Database (Best Long-term)
1. ✅ Set up Supabase account (free tier)
2. ✅ Create tables matching SQLite schema
3. ✅ Implement hybrid sync (local + cloud)
4. ✅ Add environment variable toggle

### Phase 3: Optional Enhancements
1. ⚠️ Manual correction UI (let users fix OCR mistakes)
2. ⚠️ Browser automation (auto-capture from PrizePicks)
3. ⚠️ Historical trend charts
4. ⚠️ Export/import functionality

---

## Implementation Priority

**High Priority:**
1. Image preprocessing ← Biggest accuracy boost
2. Multi-screenshot support ← User requested
3. Confidence filtering ← Reduce false positives

**Medium Priority:**
4. Multi-engine voting ← Better accuracy but slower
5. Supabase integration ← Solves centralization

**Low Priority:**
6. GitHub database ← Creative but not ideal
7. Browser automation ← Complex, maintenance burden

---

## Quick Wins (Can Implement Now)

### 1. Add OpenCV Preprocessing
```bash
pip install opencv-python-headless
```

### 2. Support Multiple Files
Already easy - just modify the upload endpoint

### 3. Better Heuristics
Improve player name / line detection thresholds

Would you like me to implement the optimized OCR system with preprocessing and multi-screenshot support right now?
