"""Growth analysis: computed metrics (deterministic) + an LLM written summary.

The numbers are computed in pure pandas so they are exact and reproducible.
OpenRouter is used ONLY to phrase the narrative — it is told to rely solely
on the figures we pass in, never to invent data.
"""
from __future__ import annotations

import pandas as pd


def engagement_rate(row) -> float | None:
    """(likes + comments) / views, as a percentage. None if no view data."""
    views = row.get("views")
    if not views or pd.isna(views) or views == 0:
        return None
    likes = row.get("likes") or 0
    comments = row.get("comments") or 0
    return round((likes + comments) / views * 100, 2)


def per_post_table(latest: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns to the latest-metrics frame for display."""
    if latest.empty:
        return latest
    df = latest.copy()
    df["engagement_rate_%"] = df.apply(engagement_rate, axis=1)
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce", utc=True)
    df = df.sort_values("published_at", ascending=False)
    return df


def account_summary(latest: pd.DataFrame) -> pd.DataFrame:
    """Overall performance per account."""
    if latest.empty:
        return latest
    df = latest.copy()
    agg = (
        df.groupby(["platform", "account"])
        .agg(
            posts=("id", "count"),
            total_views=("views", "sum"),
            total_likes=("likes", "sum"),
            total_comments=("comments", "sum"),
            avg_views=("views", "mean"),
            avg_likes=("likes", "mean"),
        )
        .reset_index()
    )
    agg["avg_eng_rate_%"] = agg.apply(
        lambda r: round((r["total_likes"] + r["total_comments"]) / r["total_views"] * 100, 2)
        if r["total_views"] else None,
        axis=1,
    )
    for c in ["total_views", "total_likes", "total_comments", "avg_views", "avg_likes"]:
        agg[c] = agg[c].round(0).astype("Int64")
    return agg


def growth_since(history: pd.DataFrame, hours: int = 24) -> pd.DataFrame:
    """View growth per post over the last `hours`, from snapshot deltas."""
    if history.empty:
        return pd.DataFrame()
    h = history.copy()
    h["captured_at"] = pd.to_datetime(h["captured_at"], utc=True, errors="coerce")
    h = h.dropna(subset=["captured_at"])
    cutoff = h["captured_at"].max() - pd.Timedelta(hours=hours)
    rows = []
    for pid, g in h.groupby("post_id"):
        g = g.sort_values("captured_at")
        recent = g[g["captured_at"] >= cutoff]
        if len(recent) < 2:
            continue
        first, last = recent.iloc[0], recent.iloc[-1]
        rows.append(
            {
                "post_id": pid,
                "title": last.get("title"),
                "platform": last.get("platform"),
                "views_gained": (last["views"] or 0) - (first["views"] or 0),
                "likes_gained": (last["likes"] or 0) - (first["likes"] or 0),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("views_gained", ascending=False)


def llm_insights(account_df: pd.DataFrame, top_posts: pd.DataFrame) -> str:
    """Ask OpenRouter to narrate the precomputed figures. Lazy-imported so the
    dashboard still works (numbers only) without an OpenRouter key."""
    from clients import get_openrouter, OPENROUTER_MODEL

    facts = (
        "ACCOUNT SUMMARY:\n" + account_df.to_string(index=False)
        + "\n\nTOP POSTS (last 10 days, by latest views):\n"
        + top_posts.to_string(index=False)
    )
    client = get_openrouter()
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a social-media growth analyst. Using ONLY the figures "
                    "provided, write a concise growth analysis: what's performing, "
                    "engagement patterns, and 3 concrete recommendations. Never "
                    "invent numbers not present. Note that share counts are "
                    "unavailable for public pages."
                ),
            },
            {"role": "user", "content": facts},
        ],
    )
    return resp.choices[0].message.content or ""
