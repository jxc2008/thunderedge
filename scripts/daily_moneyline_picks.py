#!/usr/bin/env python3
"""
Daily scraper for upcoming Americas+China moneyline picks.
Scrapes VLR for current events, fetches Thunderpick odds, runs strategy.

Run daily via cron or Task Scheduler:
  python scripts/daily_moneyline_picks.py

Output: prints BET/SKIP for each match with odds. Optionally --export to CSV.
"""

import sys
import os
import csv
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.moneyline_analytics import get_upcoming_picks


def main():
    print("=" * 60)
    print("  Daily Moneyline Picks (Americas + China)")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 60)
    data = get_upcoming_picks()
    if not data.get('success'):
        print("Error:", data.get('message', data.get('error', 'Unknown')))
        sys.exit(1)
    picks = data.get('picks', [])
    if not picks:
        print("No upcoming matches with odds found.")
        sys.exit(0)
    bets = [p for p in picks if p['decision'] == 'bet_fav']
    print(f"\n{len(picks)} matches with odds · {len(bets)} strategy bets\n")
    for p in picks:
        dec = "BET" if p['decision'] == 'bet_fav' else "SKIP"
        print(f"  [{dec}] {p['team1']} vs {p['team2']} | {p['event_name']} | Of={p['Of']} Ou={p['Ou']} p_fair={p['p_fair']}")
    if '--export' in sys.argv:
        out_path = os.path.join(os.path.dirname(__file__), 'daily_picks.csv')
        with open(out_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=['team1', 'team2', 'event_name', 'region', 'Of', 'Ou', 'p_fair', 'decision', 'stake'])
            w.writeheader()
            w.writerows(picks)
        print(f"\nExported to {out_path}")


if __name__ == '__main__':
    main()
