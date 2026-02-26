#!/usr/bin/env python3
"""
Remove moneyline matches that were incorrectly labeled due to wrong VLR event URLs.
(e.g. Funhaver matches saved as "Masters Madrid" when /event/2147 redirected to Funhaver)
Run: python scripts/cleanup_moneyline_wrong_events.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config


def main():
    import sqlite3
    conn = sqlite3.connect(Config.DATABASE_PATH)
    cur = conn.cursor()

    # Remove matches where event_name suggests VCT/International but match_url is from Funhaver
    cur.execute('''
        DELETE FROM moneyline_matches
        WHERE (event_name = 'Masters Madrid' AND match_url LIKE '%funhaver%')
           OR (event_name = 'Valorant Champions 2024' AND (match_url LIKE '%funhaver%' OR match_url LIKE '%plain-jane%'))
    ''')
    deleted = cur.rowcount
    conn.commit()
    conn.close()

    print(f"Removed {deleted} mislabeled moneyline matches (Funhaver/Plain Jane with wrong event_name).")


if __name__ == '__main__':
    main()
