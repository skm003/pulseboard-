"""SQLite storage for post identities and time-series metric snapshots.

Two tables:
  posts      - one row per post (stable identity + metadata)
  snapshots  - many rows per post (metrics captured each hourly run)

Storing snapshots is what makes this a *tracker*: we can compute growth
(deltas between captures) and draw trend lines over time.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

import pandas as pd

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id           TEXT PRIMARY KEY,   -- "{platform}:{native_id}"
    platform     TEXT NOT NULL,      -- 'instagram' | 'youtube'
    account      TEXT NOT NULL,      -- handle / channel
    native_id    TEXT NOT NULL,
    url          TEXT,
    title        TEXT,               -- caption (IG) or title (YT)
    post_type    TEXT,               -- reel/image/sidecar/video/short
    published_at TEXT,               -- ISO 8601
    thumbnail    TEXT,               -- preview image URL
    first_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id     TEXT NOT NULL REFERENCES posts(id),
    captured_at TEXT NOT NULL,       -- ISO 8601 (UTC)
    views       INTEGER,             -- NULL when platform doesn't expose
    likes       INTEGER,
    comments    INTEGER,
    shares      INTEGER              -- almost always NULL for public pages
);

CREATE INDEX IF NOT EXISTS idx_snap_post ON snapshots(post_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform, account);
"""


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Migration for older DBs created before the thumbnail column existed.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(posts)")}
        if "thumbnail" not in cols:
            conn.execute("ALTER TABLE posts ADD COLUMN thumbnail TEXT")


def upsert_post(conn, post: dict, now_iso: str) -> None:
    """Insert post if new; otherwise refresh mutable metadata."""
    conn.execute(
        """
        INSERT INTO posts (id, platform, account, native_id, url, title,
                           post_type, published_at, thumbnail, first_seen)
        VALUES (:id, :platform, :account, :native_id, :url, :title,
                :post_type, :published_at, :thumbnail, :first_seen)
        ON CONFLICT(id) DO UPDATE SET
            url=excluded.url,
            title=excluded.title,
            post_type=excluded.post_type,
            published_at=excluded.published_at,
            thumbnail=excluded.thumbnail
        """,
        {**post, "first_seen": now_iso},
    )


def add_snapshot(conn, post_id: str, now_iso: str, metrics: dict) -> None:
    conn.execute(
        """
        INSERT INTO snapshots (post_id, captured_at, views, likes, comments, shares)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            now_iso,
            metrics.get("views"),
            metrics.get("likes"),
            metrics.get("comments"),
            metrics.get("shares"),
        ),
    )


# ---- read helpers (return pandas DataFrames for the dashboard) ----

def latest_metrics(platform: str | None = None) -> pd.DataFrame:
    """Most recent snapshot per post, joined with post metadata."""
    q = """
    SELECT p.*, s.captured_at, s.views, s.likes, s.comments, s.shares
    FROM posts p
    JOIN snapshots s ON s.post_id = p.id
    JOIN (
        SELECT post_id, MAX(captured_at) AS mx
        FROM snapshots GROUP BY post_id
    ) last ON last.post_id = s.post_id AND last.mx = s.captured_at
    """
    params: tuple = ()
    if platform:
        q += " WHERE p.platform = ?"
        params = (platform,)
    q += " ORDER BY p.published_at DESC"
    with connect() as conn:
        return pd.read_sql_query(q, conn, params=params)


def snapshot_history(post_id: str) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT captured_at, views, likes, comments FROM snapshots "
            "WHERE post_id = ? ORDER BY captured_at",
            conn,
            params=(post_id,),
        )


def all_history() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            """SELECT p.platform, p.account, p.id AS post_id, p.title,
                      s.captured_at, s.views, s.likes, s.comments
               FROM posts p JOIN snapshots s ON s.post_id = p.id
               ORDER BY s.captured_at""",
            conn,
        )
