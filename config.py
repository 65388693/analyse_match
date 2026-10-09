"""
config.py
Configuration globale du projet.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# API
FC_API_KEY = os.getenv("FC_API_KEY")
LIVE_FOOTBALL_KEY = os.getenv("LIVE_FOOTBALL_KEY", "")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PRODUCTION = APP_ENV == "production" or os.getenv("RENDER") == "true"
WEB_AUTH_USERNAME = os.getenv("WEB_AUTH_USERNAME", "")
WEB_AUTH_PASSWORD = os.getenv("WEB_AUTH_PASSWORD", "")

if not FC_API_KEY and not IS_PRODUCTION:
    raise Exception("❌ FC_API_KEY manquante dans .env")
if IS_PRODUCTION and not FC_API_KEY:
    raise RuntimeError("FC_API_KEY doit être configurée dans l'environnement de production")
if IS_PRODUCTION and (not WEB_AUTH_USERNAME or not WEB_AUTH_PASSWORD):
    raise RuntimeError("WEB_AUTH_USERNAME et WEB_AUTH_PASSWORD sont obligatoires en production")

MCP_BASE = "https://mcp.football-charts.com/mcp"

# MODÈLE
MAX_GOALS = 8
HOME_ADVANTAGE = 1.15
MIN_MATCHS_FORME = 5

# CHEMINS
CACHE_DIR = os.getenv("CACHE_DIR", "cache")
DATA_DIR = os.getenv("DATA_DIR", "data")
ANALYSES_FILE = os.path.join(DATA_DIR, "analyses.json")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)