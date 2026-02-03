# frontend/app.py
"""
Frontend Flask application (alternative entry point).

This file is kept for convenience, but it now runs the main backend server
so routes like `/team` and `/api/team/<team>` exist when you start this entrypoint.
"""
import os
import sys

# Ensure project root is importable
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from backend.api import app  # noqa: E402

if __name__ == '__main__':
    # Keep the historical port for this entry point.
    app.run(debug=True, port=5001)
