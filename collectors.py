"""Apify-based collectors for Instagram and YouTube public pages.

Each collector returns a list of normalized post dicts:
    {
      "platform", "account", "native_id", "url", "title",
      "post_type", "published_at" (ISO),
      "views", "likes", "comments", "shares"  (ints or None)
    }

Accuracy notes:
  * "shares" is None for both platforms — public APIs/scrapers don't expose it.
  * Instagram image posts have no "views"; Reels/videos do.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from clients import get_apify, run_dataset_id, run_cost_usd
from config import IG_ACTOR, YT_ACTOR

# Accumulates the USD cost of actor runs in the current process (for logging).
LAST_RUN_COST = {"usd": 0.0}


def _cutoff(lookback_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=lookback_days)


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):  # unix seconds
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _duration_seconds(value) -> int | None:
    """Parse 'HH:MM:SS' or 'MM:SS' into seconds."""
    if not value or not isinstance(value, str) or ":" not in value:
        return None
    try:
        parts = [int(p) for p in value.split(":")]
    except ValueError:
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


# --------------------------- Instagram ---------------------------

def _use_rapidapi() -> bool:
    import os
    return bool(os.environ.get("RAPIDAPI_KEY", "").strip())


def collect_instagram(username: str, lookback_days: int) -> list[dict]:
    if _use_rapidapi():
        from rapidapi_collectors import ig_posts
        return ig_posts(username, lookback_days)
    client = get_apify()
    run_input = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts",
        "resultsLimit": 48,
        "addParentData": False,
    }
    # More memory = more CPU share = faster runs.
    run = client.actor(IG_ACTOR).call(run_input=run_input, memory_mbytes=4096)
    LAST_RUN_COST["usd"] += run_cost_usd(run) or 0.0
    items = client.dataset(run_dataset_id(run)).iterate_items()

    cutoff = _cutoff(lookback_days)
    out: list[dict] = []
    for it in items:
        published = _parse_dt(it.get("timestamp"))
        if published and published < cutoff:
            continue
        native_id = it.get("id") or it.get("shortCode") or it.get("shortcode")
        if not native_id:
            continue
        post_type = (it.get("type") or it.get("productType") or "").lower()
        out.append(
            {
                "platform": "instagram",
                "account": username,
                "native_id": str(native_id),
                "url": it.get("url") or f"https://www.instagram.com/p/{it.get('shortCode')}/",
                "title": (it.get("caption") or "")[:500],
                "post_type": post_type or "post",
                "published_at": published.isoformat() if published else None,
                "thumbnail": it.get("displayUrl") or it.get("thumbnailUrl"),
                # IG's headline "views" for Reels is now plays; fall back to views.
                "views": _to_int(it.get("videoPlayCount") or it.get("videoViewCount")),
                "likes": _to_int(it.get("likesCount")),
                "comments": _to_int(it.get("commentsCount")),
                "shares": None,  # not exposed publicly
            }
        )
    return out


# --------------------------- YouTube ---------------------------

def collect_youtube(channel_url: str, lookback_days: int) -> list[dict]:
    if _use_rapidapi():
        from rapidapi_collectors import yt_videos
        return yt_videos(channel_url, lookback_days)
    client = get_apify()
    # We only need the most recent ~10 days. Capping results and skipping
    # subtitles/comments/streams cuts the per-video work that makes YT slow.
    run_input = {
        "startUrls": [{"url": channel_url}],
        "maxResults": 25,
        "maxResultsShorts": 15,
        "maxResultStreams": 0,
        "sortVideosBy": "NEWEST",
        "downloadSubtitles": False,
        "saveSubsToKVS": False,
    }
    run = client.actor(YT_ACTOR).call(run_input=run_input, memory_mbytes=4096)
    LAST_RUN_COST["usd"] += run_cost_usd(run) or 0.0
    items = client.dataset(run_dataset_id(run)).iterate_items()

    cutoff = _cutoff(lookback_days)
    out: list[dict] = []
    for it in items:
        published = _parse_dt(it.get("date") or it.get("uploadDate") or it.get("publishedAt"))
        if published and published < cutoff:
            continue
        native_id = it.get("id") or it.get("videoId")
        if not native_id:
            continue
        dur = _duration_seconds(it.get("duration"))
        is_short = (
            bool(it.get("isShort"))
            or "short" in str(it.get("type", "")).lower()
            or (dur is not None and dur <= 60)
        )
        out.append(
            {
                "platform": "youtube",
                "account": it.get("channelName") or channel_url,
                "native_id": str(native_id),
                "url": it.get("url") or f"https://www.youtube.com/watch?v={native_id}",
                "title": (it.get("title") or "")[:500],
                "post_type": "short" if is_short else "video",
                "published_at": published.isoformat() if published else None,
                "thumbnail": it.get("thumbnailUrl") or it.get("thumbnail"),
                "views": _to_int(it.get("viewCount") or it.get("views")),
                "likes": _to_int(it.get("likes") or it.get("likeCount")),
                "comments": _to_int(it.get("commentsCount") or it.get("numberOfComments")),
                "shares": None,  # not exposed publicly
            }
        )
    return out
