# IG + YouTube Performance Tracker

A local dashboard that tracks the **last 10 days of posts** for public Instagram
and YouTube pages, refreshing **every hour** and storing **historical snapshots**
so you get real growth trend lines (not just a single reading).

## What it tracks (accurately)

| Metric | Instagram | YouTube |
|---|---|---|
| Views (reels/videos) | ✅ | ✅ |
| Likes | ✅ | ✅ |
| Comments | ✅ | ✅ |
| Post date | ✅ | ✅ |
| Engagement rate (computed) | ✅ | ✅ |
| Growth over time (per snapshot) | ✅ | ✅ |
| **Shares** | ❌ not public | ❌ not public |

> Share counts are **not exposed publicly** by either platform, so they are
> intentionally omitted rather than guessed. (They are only available via the
> owner's private analytics APIs.)

## Setup

1. Put your keys in `.env` (already created):
   - `APIFY_TOKEN` — set ✅
   - `OPENROUTER_API_KEY` — needed only for the optional AI written analysis
2. Edit `accounts.json` with the pages you want to track.
3. Install deps: `pip install -r requirements.txt`

## Run

```powershell
# 1. Start hourly collection (keep running in one terminal)
python scheduler.py

# 2. In another terminal, open the dashboard
streamlit run dashboard.py
```

Or collect once manually: `python collect.py`

## Files

- `accounts.json` — pages to track + lookback window
- `clients.py` — Apify + OpenRouter clients
- `collectors.py` — Instagram + YouTube scraping (normalized output)
- `collect.py` — one collection pass → writes snapshots to SQLite
- `scheduler.py` — runs `collect` now + every hour
- `db.py` — SQLite schema + read helpers
- `analysis.py` — computed metrics (exact) + optional LLM narrative
- `dashboard.py` — Streamlit UI (KPIs, per-post table, trends, movers)
- `tracker.db` — local SQLite database (auto-created)

## Cost note

Apify scraping consumes credits (your account is on the FREE $5/month plan).
Each hourly pass runs one actor per page. If you track many pages, consider a
longer interval — edit `hours=1` in `scheduler.py`.
