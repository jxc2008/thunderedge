#!/usr/bin/env python3
"""
Valorant KPR Betting Analysis Tool
Run: python run.py
"""

import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api import app
from scraper.vlr_scraper import VLRScraper
import webbrowser
import threading
import time

def open_browser():
    """Open browser to frontend after delay"""
    time.sleep(2)
    webbrowser.open('http://localhost:5000')

if __name__ == '__main__':
    print("=" * 60)
    print("  Valorant KPR Betting Analysis Tool")
    print("=" * 60)
    print()
    print("  Backend API running on http://localhost:5000")
    print("  Frontend available at http://localhost:5000")
    print()
    print("  Example API queries:")
    print("    - http://localhost:5000/api/player/TenZ?line=0.75")
    print("    - http://localhost:5000/api/player/aspas?line=0.70")
    print()
    print("  Press Ctrl+C to stop the server")
    print("=" * 60)
    
    # Open browser automatically
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Debug: Print all routes
    print("\nRegistered routes:")
    for rule in sorted(app.url_map.iter_rules(), key=lambda x: x.rule):
        print(f"  {rule.rule} -> {rule.endpoint}")
    print()
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)
