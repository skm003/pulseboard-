"""Run one collection pass: scrape configured + previously-searched accounts.

    python collect.py            # one pass now
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from config import load_accounts
from collectors import collect_instagram, collect_youtube
from db import init_db, save_posts, record_target, list_tracked_targets


def _scrape(platform: str, target: str, lookback_days: int) -> list[dict]:
    fn = collect_instagram if platform == "instagram" else collect_youtube
    posts = fn(target, lookback_days)
    for p in posts:
        p["id"] = f"{p['platform']}:{p['native_id']}"
    return posts


def collect_target(platform: str, target: str, lookback_days: int = 10) -> dict:
    """Scrape a SINGLE account on demand (used by the dashboard search bar)."""
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    posts = _scrape(platform, target, lookback_days)
    save_posts(posts, now_iso)
    record_target(platform, target, now_iso)  # remember it for the cron
    accounts = sorted({p["account"] for p in posts})
    return {
        "platform": platform,
        "target": target,
        "posts": len(posts),
        "accounts": accounts,
        "post_ids": [p["id"] for p in posts],
    }


def run_once() -> dict:
    """Refresh the watch-list AND every previously-searched account, so
    Trends/Movers build for all ids."""
    init_db()
    cfg = load_accounts()
    lookback = cfg["lookback_days"]
    now_iso = datetime.now(timezone.utc).isoformat()
    stats = {"instagram": 0, "youtube": 0, "errors": []}

    # watch-list from accounts.json + every account ever searched
    jobs: list[tuple[str, str]] = (
        [("instagram", h) for h in cfg["instagram"]]
        + [("youtube", u) for u in cfg["youtube"]]
        + list_tracked_targets()
    )
    seen = set()
    for platform, target in jobs:
        key = (platform, target)
        if key in seen:
            continue
        seen.add(key)
        try:
            print(f"[collect] {platform}: {target}", file=sys.stderr)
            posts = _scrape(platform, target, lookback)
            save_posts(posts, now_iso)
            stats[platform] += len(posts)
            print(f"[collect]   -> {len(posts)} posts", file=sys.stderr)
        except Exception as e:  # noqa: BLE001
            msg = f"{platform}:{target} -> {e!r}"
            stats["errors"].append(msg)
            print(f"[collect]   ERROR {msg}", file=sys.stderr)

    print(f"[collect] done at {now_iso}: {stats}", file=sys.stderr)
    return stats


if __name__ == "__main__":
    run_once()
