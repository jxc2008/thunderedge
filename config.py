# config.py
import os
from datetime import timedelta

# Load .env for GOOGLE_API_KEY (PrizePicks vision parsing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Force-disable proxy environment variables.
# This project scrapes VLR.gg and proxy env vars frequently break requests on Windows
# (e.g. misconfigured HTTP(S)_PROXY pointing to 127.0.0.1:9).
for _k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(_k, None)
# Ensure requests/urllib bypass proxy for all hosts by default
os.environ.setdefault('NO_PROXY', '*')
os.environ.setdefault('no_proxy', '*')

# Get the directory where this config file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    # Scraping settings
    VLR_BASE_URL = "https://www.vlr.gg"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # Database - supports environment variable for deployment
    # Default to local path, but can be overridden with DATABASE_PATH env var
    DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(BASE_DIR, "data", "valorant_stats.db"))
    
    # Calculation settings
    DEFAULT_KILL_LINE = 15.5  # Default kill line from sportsbook (over/under kills)
    
    # Rounds needed classification thresholds
    ROUNDS_THRESHOLDS = {
        'severely_underpriced': 19,      # < 19 rounds
        'moderately_underpriced': 20,    # 19-20 rounds
        'slightly_underpriced': 20.5,    # 20-20.5 rounds
        'well_priced_upper': 23.5,       # 20.5-23.5 rounds (fair value)
        'slightly_overpriced': 24,       # 23.5-24 rounds
        'moderately_overpriced': 25,     # 24-25 rounds
        # > 25 rounds = severely overpriced
    }
    
    # Cache settings
    CACHE_DURATION = timedelta(hours=6)
    
    # (Legacy - was used by OCR) Team name fragments - kept for reference
    OCR_TEAM_BLACKLIST = frozenset([
        # Pacific/Asia
        'rex', 'regum', 'qeon', 'nongshim', 'redforce', 'gentle', 'mates',
        'paper', 'canids', 'drx', 'prx', 'zeta', 'bleed', 'talon', 'geng',
        'secret', 'boom', 'onic', 'rrq', 'xerxia', 'kru', 'bbl',
        # Americas
        'liquid', 'sentinels', 'loud', 'optic', 'leviatan', 'cloud9', 'c9',
        'furia', 'academy', 'heretics', 'mibr', '100t', 'nrg', 'eg',
        'evi', 'complexity', 'col', 'g2', 'kru',
        # Challengers / common OCR mixups (team names mistaken for players)
        'sleepers', '9z', 'sorex', 'solada', 'tonza',
        # EMEA / team fragments OCR often picks up
        'fnatic', 'vitality', 'karmine', 'karmi', 'koi', 'g2', 'navi', 'fpx', 'natus', 'vincere',
        # UI / date labels OCR misreads as player names
        'today', 'tomorrow', 'yesterday',
        # UI labels
        'player', 'team', 'line', 'best', 'samples', 'prob', 'hit',
        'maps', 'kills', 'vs', 'am', 'pm', 'over', 'under',
        'thu', 'fri', 'sat', 'sun', 'mon', 'tue', 'wed',
        'valorant', 'vct', 'esports', 'game', 'view', 'history',
        'versus', 'match',
    ])
