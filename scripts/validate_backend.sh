#!/usr/bin/env bash
# Validation gate for backend/data changes.
# Agents MUST run this and pass before reporting a task done.
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Backend Validation ==="

echo "[1/3] Python syntax check (backend)..."
python -m py_compile backend/api.py
python -m py_compile backend/database.py
python -m py_compile backend/model_params.py
python -m py_compile backend/prop_prob.py
python -m py_compile backend/matchup_adjust.py
python -m py_compile backend/odds_utils.py
python -m py_compile backend/calculator.py
echo "  PASS"

echo "[2/3] Flask app import check..."
python -c "
import sys; sys.path.insert(0, '.')
from backend.api import app
print('  Flask app loaded OK, routes:', len(list(app.url_map.iter_rules())))
"

echo "[3/3] Database import + schema check..."
python -c "
import sys; sys.path.insert(0, '.')
from backend.database import Database
from config import Config
db = Database(Config.DATABASE_PATH)
stats = db.get_stats()
print('  DB OK, events:', stats.get('vct_events'), '| matches:', stats.get('matches_cached'))
"

echo "=== All backend checks passed ==="
