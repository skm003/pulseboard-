"""Run one collection pass: scrape all configured accounts and write snapshots.

    python collect.py            # one pass now
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from config import load_accounts
from collectors import collect_instagram, collect_youtube
from db import init_db, connect, upsert_post, add_snapshot


def collect_target(platform: str, target: str, lookback_days: int = 10) -> dict:
    """Scrape a SINGLE account on demand (used by the dashboard search bar).

    platform: 'instagram' or 'youtube'
    target:   IG username (no @) or YouTube channel URL/@handle
    """
    init_db()
    now_iso = datetime.now(timezone.utc).isoformat()
    fn = collect_instagram if platform == "instagram" else collect_youtube

    posts = fn(target, lookback_days)
    accounts = set()
    post_ids = []
    with connect() as conn:
        for p in posts:
            p["id"] = f"{p['platform']}:{p['native_id']}"
            upsert_post(conn, p, now_iso)
            add_snapshot(conn, p["id"], now_iso, p)
            accounts.add(p["account"])
            post_ids.append(p["id"])
    return {
        "platform": platform,
        "target": target,
        "posts": len(posts),
        "accounts": sorted(accounts),
        "post_ids": post_ids,
    }


def run_once() -> dict:
    init_db()
    cfg = load_accounts()
    lookback = cfg["lookback_days"]
    now_iso = datetime.now(timezone.utc).isoformat()

    stats = {"instagram": 0, "youtube": 0, "errors": []}

    jobs = (
        [("instagram", collect_instagram, h) for h in cfg["instagram"]]
        + [("youtube", collect_youtube, u) for u in cfg["youtube"]]
    )

    for platform, fn, target in jobs:
        try:
            print(f"[collect] {platform}: {target}", file=sys.stderr)
            posts = fn(target, lookback)
            with connect() as conn:
                for p in posts:
                    p["id"] = f"{p['platform']}:{p['native_id']}"
                    upsert_post(conn, p, now_iso)
                    add_snapshot(conn, p["id"], now_iso, p)
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
