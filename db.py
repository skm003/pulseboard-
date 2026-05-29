"""Storage layer with a dual backend.

* If TURSO_DATABASE_URL is set  -> uses Turso (hosted libSQL/SQLite) so the
  deployed app AND the GitHub Actions cron share ONE database. Every account
  you search builds persistent history -> Trends & Movers work for all ids.
* Otherwise                      -> local SQLite file (great for dev).

Tables:
  posts            - one row per post (identity + metadata)
  snapshots        - many rows per post (metrics captured over time)
  tracked_targets  - every account ever searched, so the cron can keep
                     refreshing them and build trends for all of them.
"""
from __future__ import annotations

import os
import sqlite3

import pandas as pd

from config import DB_PATH

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "").strip()
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
USE_TURSO = bool(TURSO_URL)

SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS posts (
        id           TEXT PRIMARY KEY,
        platform     TEXT NOT NULL,
        account      TEXT NOT NULL,
        native_id    TEXT NOT NULL,
        url          TEXT,
        title        TEXT,
        post_type    TEXT,
        published_at TEXT,
        thumbnail    TEXT,
        first_seen   TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id     TEXT NOT NULL,
        captured_at TEXT NOT NULL,
        views       INTEGER,
        likes       INTEGER,
        comments    INTEGER,
        shares      INTEGER
    )""",
    """CREATE TABLE IF NOT EXISTS tracked_targets (
        id            TEXT PRIMARY KEY,
        platform      TEXT NOT NULL,
        target        TEXT NOT NULL,
        last_searched TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_snap_post ON snapshots(post_id, captured_at)",
    "CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform, account)",
]


# --------------------------- backend primitives ---------------------------

def _turso_client():
    import libsql_client
    # Use HTTP transport (more reliable than the default websocket): map the
    # libsql:// scheme Turso hands out to https://.
    url = TURSO_URL
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return libsql_client.create_client_sync(url=url, auth_token=TURSO_TOKEN or None)


def _write_batch(statements: list[tuple]) -> None:
    """Run a list of (sql, params) write statements atomically."""
    if not statements:
        return
    if USE_TURSO:
        client = _turso_client()
        try:
            client.batch([(sql, list(params)) for sql, params in statements])
        finally:
            client.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            for sql, params in statements:
                conn.execute(sql, tuple(params))
            conn.commit()
        finally:
            conn.close()


def _execute(sql: str, params=()) -> None:
    """Run a single write statement (errors propagate)."""
    if USE_TURSO:
        client = _turso_client()
        try:
            client.execute(sql, list(params))
        finally:
            client.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(sql, tuple(params))
            conn.commit()
        finally:
            conn.close()


def _read_df(sql: str, params=()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame (backend-agnostic)."""
    if USE_TURSO:
        client = _turso_client()
        try:
            rs = client.execute(sql, list(params))
            return pd.DataFrame([tuple(r) for r in rs.rows], columns=list(rs.columns))
        finally:
            client.close()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(sql, tuple(params))
        cols = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)
    finally:
        conn.close()


# --------------------------- schema / writes ---------------------------

def init_db() -> None:
    _write_batch([(s, ()) for s in SCHEMA_STATEMENTS])
    # Migration for older local DBs created before the thumbnail column.
    try:
        _execute("ALTER TABLE posts ADD COLUMN thumbnail TEXT")
    except Exception:  # noqa: BLE001 - column already exists
        pass


_UPSERT_POST = """
INSERT INTO posts (id, platform, account, native_id, url, title,
                   post_type, published_at, thumbnail, first_seen)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    url=excluded.url, title=excluded.title, post_type=excluded.post_type,
    published_at=excluded.published_at, thumbnail=excluded.thumbnail
"""

_INSERT_SNAPSHOT = """
INSERT INTO snapshots (post_id, captured_at, views, likes, comments, shares)
VALUES (?, ?, ?, ?, ?, ?)
"""


def save_posts(posts: list[dict], now_iso: str) -> None:
    """Upsert posts and append a metrics snapshot for each."""
    stmts: list[tuple] = []
    for p in posts:
        pid = p.get("id") or f"{p['platform']}:{p['native_id']}"
        stmts.append((_UPSERT_POST, (
            pid, p["platform"], p["account"], p["native_id"], p.get("url"),
            p.get("title"), p.get("post_type"), p.get("published_at"),
            p.get("thumbnail"), now_iso,
        )))
        stmts.append((_INSERT_SNAPSHOT, (
            pid, now_iso, p.get("views"), p.get("likes"),
            p.get("comments"), p.get("shares"),
        )))
    _write_batch(stmts)


def record_target(platform: str, target: str, now_iso: str) -> None:
    """Remember a searched account so the cron keeps building its history."""
    _execute(
        """INSERT INTO tracked_targets (id, platform, target, last_searched)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET last_searched=excluded.last_searched""",
        (f"{platform}:{target}", platform, target, now_iso),
    )


def list_tracked_targets(limit: int = 40) -> list[tuple[str, str]]:
    """Most-recently-searched (platform, target) pairs for the cron to refresh."""
    df = _read_df(
        "SELECT platform, target FROM tracked_targets "
        "ORDER BY last_searched DESC LIMIT ?",
        (limit,),
    )
    return list(df.itertuples(index=False, name=None)) if not df.empty else []


# --------------------------- reads (DataFrames) ---------------------------

def latest_metrics(platform: str | None = None) -> pd.DataFrame:
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
    return _read_df(q, params)


def snapshot_history(post_id: str) -> pd.DataFrame:
    return _read_df(
        "SELECT captured_at, views, likes, comments FROM snapshots "
        "WHERE post_id = ? ORDER BY captured_at",
        (post_id,),
    )


def all_history() -> pd.DataFrame:
    return _read_df(
        """SELECT p.platform, p.account, p.id AS post_id, p.title,
                  s.captured_at, s.views, s.likes, s.comments
           FROM posts p JOIN snapshots s ON s.post_id = p.id
           ORDER BY s.captured_at"""
    )
