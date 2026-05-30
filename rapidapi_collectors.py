"""Free RapidAPI collectors (used when RAPIDAPI_KEY is set).

Instagram : instagram-scraper-stable-api  -> likes, comments, date, thumb
            (this free API does not expose view counts)
YouTube   : yt-api                        -> views, date, thumb, duration
            (likes/comments omitted to stay within free call limits)

Same normalized output shape as the Apify collectors in collectors.py.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

IG_HOST = os.environ.get("RAPIDAPI_IG_HOST", "instagram-scraper-stable-api.p.rapidapi.com")
YT_HOST = os.environ.get("RAPIDAPI_YT_HOST", "yt-api.p.rapidapi.com")


def _key() -> str:
    k = os.environ.get("RAPIDAPI_KEY", "").strip()
    if not k:
        raise RuntimeError("RAPIDAPI_KEY is not set.")
    return k


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def _to_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get(host: str, path: str):
    req = urllib.request.Request(
        f"https://{host}{path}",
        headers={"x-rapidapi-host": host, "x-rapidapi-key": _key()},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _post(host: str, path: str, form: dict):
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        f"https://{host}{path}", data=body,
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "x-rapidapi-host": host, "x-rapidapi-key": _key(),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ------------------------------- Instagram -------------------------------

_IG_TYPE = {1: "image", 2: "reel", 8: "sidecar"}


def ig_posts(username: str, lookback_days: int) -> list[dict]:
    data = _post(IG_HOST, "/get_ig_user_posts.php", {
        "username_or_url": f"https://www.instagram.com/{username}/",
        "amount": "48",
    })
    cutoff = _cutoff(lookback_days)
    out: list[dict] = []
    for item in data.get("posts", []):
        n = item.get("node", item)
        taken = n.get("taken_at")
        published = datetime.fromtimestamp(taken, tz=timezone.utc) if taken else None
        if published and published < cutoff:
            continue
        native_id = n.get("pk") or n.get("id") or n.get("code")
        if not native_id:
            continue
        cap = n.get("caption")
        title = (cap.get("text") if isinstance(cap, dict) else cap) or ""
        cands = (n.get("image_versions2") or {}).get("candidates") or []
        thumb = cands[0]["url"] if cands else n.get("display_uri")
        ptype = (n.get("product_type") or "").lower()
        post_type = "sidecar" if n.get("media_type") == 8 else _IG_TYPE.get(n.get("media_type"), "post")
        if "clip" in ptype:
            post_type = "reel"
        out.append({
            "platform": "instagram", "account": username,
            "native_id": str(native_id),
            "url": f"https://www.instagram.com/p/{n.get('code')}/" if n.get("code") else None,
            "title": title[:500], "post_type": post_type,
            "published_at": published.isoformat() if published else None,
            "thumbnail": thumb,
            "views": _to_int(n.get("view_count") or n.get("play_count") or n.get("ig_play_count")),
            "likes": _to_int(n.get("like_count")),
            "comments": _to_int(n.get("comment_count")),
            "shares": None,
        })
    return out


# ------------------------------- YouTube -------------------------------

def _channel_id(channel_url: str) -> str:
    """Resolve a channel URL/@handle to a UC... channel id."""
    if "/channel/UC" in channel_url:
        return channel_url.split("/channel/")[1].split("/")[0].split("?")[0]
    if channel_url.startswith("UC") and " " not in channel_url:
        return channel_url
    res = _get(YT_HOST, "/resolve?url=" + urllib.parse.quote(channel_url, safe=""))
    cid = res.get("browseId") or res.get("channelId")
    if not cid:
        raise RuntimeError(f"Could not resolve channel id for {channel_url}")
    return cid


def _dur_secs(text) -> int | None:
    if not text or ":" not in str(text):
        return None
    parts = [int(p) for p in str(text).split(":") if p.isdigit()]
    secs = 0
    for p in parts:
        secs = secs * 60 + p
    return secs


def yt_videos(channel_url: str, lookback_days: int) -> list[dict]:
    cid = _channel_id(channel_url)
    data = _get(YT_HOST, f"/channel/videos?id={cid}")
    channel_name = (data.get("meta") or {}).get("title") or channel_url
    cutoff = _cutoff(lookback_days)
    out: list[dict] = []
    for v in data.get("data", []):
        if v.get("type") not in (None, "video", "shorts"):
            continue
        vid = v.get("videoId")
        if not vid:
            continue
        pub = v.get("publishDate") or v.get("publishedAt")
        published = None
        if pub:
            try:
                published = datetime.fromisoformat(str(pub)[:10]).replace(tzinfo=timezone.utc)
            except ValueError:
                published = None
        if published and published < cutoff:
            continue
        thumbs = v.get("thumbnail") or []
        thumb = thumbs[-1]["url"] if thumbs else None
        dur = _dur_secs(v.get("lengthText"))
        is_short = v.get("type") == "shorts" or (dur is not None and dur <= 60)
        out.append({
            "platform": "youtube", "account": v.get("channelTitle") or channel_name,
            "native_id": str(vid),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": (v.get("title") or "")[:500],
            "post_type": "short" if is_short else "video",
            "published_at": published.isoformat() if published else None,
            "thumbnail": thumb,
            "views": _to_int(v.get("viewCount")),
            "likes": None, "comments": None, "shares": None,
        })
    return out
