#!/usr/bin/env python3
"""
Scrape VLR.gg for all Valorant Challengers (tier 2 / VCL) leagues.
Run: python scripts/scrape_challengers.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper.vlr_scraper import VLRScraper


def main():
    scraper = VLRScraper()
    print("Fetching Challengers leagues from VLR.gg (tier=61 VCL)...")
    leagues = scraper.get_challengers_leagues(max_pages=10)
    print(f"\nFound {len(leagues)} Challengers leagues:\n")
    for i, L in enumerate(leagues, 1):
        print(f"{i:3}. {L['name']}")
        print(f"     https://www.vlr.gg{L['url']}")
    print(f"\nTotal: {len(leagues)} leagues accessible.")


if __name__ == "__main__":
    main()
