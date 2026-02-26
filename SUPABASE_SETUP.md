# Supabase Setup for Centralized Leaderboard Storage

## Why Supabase?

**Problem:** SQLite database is local-only. Each machine has separate leaderboard history.

**Solution:** Supabase provides:
- ✅ Free PostgreSQL database in the cloud
- ✅ Real-time sync across all devices
- ✅ Automatic backups
- ✅ Simple REST API
- ✅ 500MB storage free tier
- ✅ Built-in authentication (if needed later)

---

## Quick Setup (5 minutes)

### 1. Create Supabase Account

1. Go to https://supabase.com
2. Sign up (free tier)
3. Create new project:
   - Name: `thunderedge-prod`
   - Database Password: (save this!)
   - Region: Choose closest to you

### 2. Create Tables

In Supabase SQL Editor, run:

```sql
-- Leaderboard snapshots table
CREATE TABLE leaderboard_snapshots (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    source TEXT NOT NULL,
    parsed_count INTEGER DEFAULT 0,
    ranked_count INTEGER DEFAULT 0
);

-- Leaderboard entries table
CREATE TABLE leaderboard_entries (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES leaderboard_snapshots(id) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    vlr_ign TEXT,
    team TEXT,
    line REAL NOT NULL,
    best_side TEXT NOT NULL,
    p_hit REAL NOT NULL,
    p_over REAL NOT NULL,
    p_under REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    mu REAL
);

-- Indexes for performance
CREATE INDEX idx_leaderboard_snapshot ON leaderboard_entries(snapshot_id);
CREATE INDEX idx_snapshots_created ON leaderboard_snapshots(created_at DESC);
CREATE INDEX idx_player_name ON leaderboard_entries(player_name);

-- Enable Row Level Security (optional, for multi-user later)
ALTER TABLE leaderboard_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE leaderboard_entries ENABLE ROW LEVEL SECURITY;

-- Allow public read access (or customize for your needs)
CREATE POLICY "Allow public read" ON leaderboard_snapshots FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON leaderboard_entries FOR SELECT USING (true);

-- Allow authenticated insert (get API key from Supabase)
CREATE POLICY "Allow authenticated insert" ON leaderboard_snapshots FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow authenticated insert" ON leaderboard_entries FOR INSERT WITH CHECK (true);
```

### 3. Get API Credentials

1. In Supabase dashboard → Settings → API
2. Copy:
   - **Project URL** (e.g., `https://abcdefgh.supabase.co`)
   - **anon/public key** (starts with `eyJ...`)

### 4. Configure ThunderEdge

Create/update `.env` file in project root:

```bash
# Supabase Configuration
USE_CLOUD_DB=true
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Keep local backup (hybrid mode)
KEEP_LOCAL_DB=true
```

### 5. Install Supabase Client

```bash
pip install supabase
```

### 6. Update `requirements.txt`

Add:
```
supabase==2.3.0  # Cloud database client
```

---

## Implementation Code

### Create `backend/cloud_db.py`:

```python
"""
Cloud database integration using Supabase.
Provides centralized leaderboard storage across all devices.
"""
import os
import logging
from typing import List, Dict, Optional
from config import Config

logger = logging.getLogger(__name__)


class CloudDatabase:
    """Supabase PostgreSQL database for centralized storage."""
    
    def __init__(self):
        self.enabled = os.getenv('USE_CLOUD_DB', 'false').lower() == 'true'
        self.supabase = None
        
        if self.enabled:
            try:
                from supabase import create_client, Client
                url = os.getenv('SUPABASE_URL')
                key = os.getenv('SUPABASE_KEY')
                
                if not url or not key:
                    logger.warning("Supabase credentials not found. Cloud DB disabled.")
                    self.enabled = False
                    return
                
                self.supabase: Client = create_client(url, key)
                logger.info("Cloud database initialized")
            except ImportError:
                logger.warning("supabase package not installed. Cloud DB disabled.")
                self.enabled = False
            except Exception as e:
                logger.error(f"Failed to initialize cloud database: {e}")
                self.enabled = False
    
    def save_leaderboard_snapshot(self, source: str, results: List[Dict], 
                                   parsed_count: int = 0) -> Optional[int]:
        """Save leaderboard snapshot to Supabase."""
        if not self.enabled or not self.supabase:
            return None
        
        try:
            # Insert snapshot
            snapshot_data = {
                'source': source,
                'parsed_count': parsed_count,
                'ranked_count': len(results)
            }
            
            response = self.supabase.table('leaderboard_snapshots').insert(snapshot_data).execute()
            snapshot_id = response.data[0]['id']
            
            # Insert entries
            entries = []
            for r in results:
                entries.append({
                    'snapshot_id': snapshot_id,
                    'rank': r['rank'],
                    'player_name': r['player_name'],
                    'vlr_ign': r.get('vlr_ign'),
                    'team': r.get('team'),
                    'line': r['line'],
                    'best_side': r['best_side'],
                    'p_hit': r['p_hit'],
                    'p_over': r['p_over'],
                    'p_under': r['p_under'],
                    'sample_size': r['sample_size'],
                    'mu': r.get('mu')
                })
            
            self.supabase.table('leaderboard_entries').insert(entries).execute()
            
            logger.info(f"Saved snapshot {snapshot_id} to cloud ({len(results)} entries)")
            return snapshot_id
            
        except Exception as e:
            logger.error(f"Error saving to cloud: {e}")
            return None
    
    def get_leaderboard_snapshots(self, limit: int = 50) -> List[Dict]:
        """Fetch recent snapshots from Supabase."""
        if not self.enabled or not self.supabase:
            return []
        
        try:
            response = self.supabase.table('leaderboard_snapshots')\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching snapshots from cloud: {e}")
            return []
    
    def get_leaderboard_snapshot(self, snapshot_id: int) -> Optional[Dict]:
        """Fetch specific snapshot with entries."""
        if not self.enabled or not self.supabase:
            return None
        
        try:
            # Get snapshot metadata
            snapshot_response = self.supabase.table('leaderboard_snapshots')\
                .select('*')\
                .eq('id', snapshot_id)\
                .execute()
            
            if not snapshot_response.data:
                return None
            
            snapshot = snapshot_response.data[0]
            
            # Get entries
            entries_response = self.supabase.table('leaderboard_entries')\
                .select('*')\
                .eq('snapshot_id', snapshot_id)\
                .order('rank')\
                .execute()
            
            snapshot['leaderboard'] = entries_response.data
            return snapshot
            
        except Exception as e:
            logger.error(f"Error fetching snapshot from cloud: {e}")
            return None
```

### Update `backend/database.py`:

Add hybrid mode:

```python
class Database:
    def __init__(self, db_path: str):
        # Existing SQLite init
        self.db_path = db_path
        self._initialize_db()
        
        # Add cloud database
        from backend.cloud_db import CloudDatabase
        self.cloud_db = CloudDatabase()
        self.keep_local = os.getenv('KEEP_LOCAL_DB', 'true').lower() == 'true'
    
    def save_leaderboard_snapshot(self, source: str, results: List[Dict], 
                                   parsed_count: int = 0) -> Optional[int]:
        """Save to both local and cloud (hybrid mode)."""
        local_id = None
        cloud_id = None
        
        # Save to local SQLite (if enabled)
        if self.keep_local:
            try:
                local_id = self._save_local_leaderboard(source, results, parsed_count)
                logger.info(f"Saved to local database: {local_id}")
            except Exception as e:
                logger.error(f"Local save failed: {e}")
        
        # Sync to cloud (if enabled)
        if self.cloud_db.enabled:
            try:
                cloud_id = self.cloud_db.save_leaderboard_snapshot(source, results, parsed_count)
                if cloud_id:
                    logger.info(f"Synced to cloud: {cloud_id}")
            except Exception as e:
                logger.warning(f"Cloud sync failed (continuing): {e}")
        
        return local_id or cloud_id
    
    def get_leaderboard_snapshots(self, limit: int = 50) -> List[Dict]:
        """Fetch from cloud first, fallback to local."""
        if self.cloud_db.enabled:
            try:
                snapshots = self.cloud_db.get_leaderboard_snapshots(limit)
                if snapshots:
                    logger.info(f"Fetched {len(snapshots)} snapshots from cloud")
                    return snapshots
            except Exception as e:
                logger.warning(f"Cloud fetch failed, using local: {e}")
        
        # Fallback to local
        return self._get_local_leaderboard_snapshots(limit)
```

---

## Testing

### Test Local → Cloud Sync:

```python
# scripts/test_cloud_sync.py
from backend.database import Database
from config import Config

db = Database(Config.DATABASE_PATH)

# Create test snapshot
test_results = [{
    'rank': 1,
    'player_name': 'TestPlayer',
    'line': 18.5,
    'best_side': 'OVER',
    'p_hit': 0.65,
    'p_over': 0.65,
    'p_under': 0.35,
    'sample_size': 30,
    'mu': 20.1
}]

snapshot_id = db.save_leaderboard_snapshot('test', test_results, parsed_count=1)
print(f"✅ Saved snapshot: {snapshot_id}")

# Fetch back
snapshots = db.get_leaderboard_snapshots(limit=5)
print(f"✅ Fetched {len(snapshots)} snapshots")
print(snapshots[0] if snapshots else "No snapshots found")
```

Run:
```bash
python scripts/test_cloud_sync.py
```

---

## Benefits

### Before (SQLite Only):
- ❌ Data on one computer only
- ❌ Lost if database corrupted
- ❌ Can't share with team

### After (Hybrid Mode):
- ✅ Automatic cloud backup
- ✅ Access from any device
- ✅ Sync across team members
- ✅ Still works offline (local backup)
- ✅ Historical data preserved forever

---

## Cost

**Free Tier:**
- 500MB database storage
- 2GB bandwidth/month
- Unlimited API requests

**For ThunderEdge:**
- Each leaderboard ~10KB
- Can store 50,000+ leaderboards free
- Plenty for years of data!

---

## Next Steps

1. ✅ Create Supabase account
2. ✅ Run SQL schema
3. ✅ Add credentials to `.env`
4. ✅ Install `supabase` package
5. ✅ Test with `test_cloud_sync.py`
6. 🎉 Enjoy centralized leaderboard history!

---

## Alternative: GitHub as Backend (No DB Setup)

If you prefer zero database setup:

```python
# Use GitHub repo to store JSON files
# See OCR_IMPROVEMENT_PLAN.md "Option C"
```

But Supabase is recommended for:
- Faster queries
- Real-time updates
- Proper database features
- Easy scaling
