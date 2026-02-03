# Vercel serverless function entry point
# This file is required for Vercel to properly handle Flask routes

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.api import app

# Vercel's @vercel/python automatically detects Flask apps
# Just export the app variable
__all__ = ['app']
