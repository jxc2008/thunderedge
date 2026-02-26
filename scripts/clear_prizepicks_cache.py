#!/usr/bin/env python3
"""
Clear PrizePicks player/combo caches so fresh 2026 data (Kickoff, Stage 1) is fetched.
Run: python scripts/clear_prizepicks_cache.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import Database
from config import Config

def main():
    db = Database(Config.DATABASE_PATH)
    counts = db.clear_prizepicks_cache(challengers_only=False)
    total = sum(counts.values())
    print(f"Cleared PrizePicks cache: {counts}")
    print(f"Total rows removed: {total}")
    print("Next OCR leaderboard upload will fetch fresh 2026 data.")

if __name__ == '__main__':
    main()
