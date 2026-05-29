"""Loads tracking config from accounts.json and Apify actor settings."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = str(ROOT / "tracker.db")

# Apify actors used for public scraping. Override via env if you prefer others.
IG_ACTOR = os.environ.get("APIFY_IG_ACTOR", "apify/instagram-scraper")
YT_ACTOR = os.environ.get("APIFY_YT_ACTOR", "streamers/youtube-scraper")


def load_accounts() -> dict:
    with open(ROOT / "accounts.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("lookback_days", 10)
    cfg.setdefault("instagram", [])
    cfg.setdefault("youtube", [])
    return cfg
