"""Instagram + YouTube performance tracker dashboard.

Run with:
    streamlit run dashboard.py

Auto-refreshes every hour to pick up the latest snapshots written by
scheduler.py. Use the sidebar button to trigger an immediate collection.
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

# --- Cloud secrets bridge -------------------------------------------------
# On Streamlit Community Cloud, credentials live in st.secrets (set via the
# app's Secrets UI). Copy them into os.environ BEFORE clients.py reads them,
# so the same code works locally (.env) and in the cloud (st.secrets).
try:
    for _k in ("APIFY_TOKEN", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
               "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "APP_PASSWORD",
               "RAPIDAPI_KEY", "RAPIDAPI_IG_HOST", "RAPIDAPI_YT_HOST"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = str(st.secrets[_k])
except Exception:  # noqa: BLE001 - no secrets file locally is fine
    pass

from db import init_db, latest_metrics, snapshot_history, all_history
from analysis import per_post_table, account_summary, growth_since

st.set_page_config(
    page_title="PulseBoard — Vaibhav Sisinty",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# PulseBoard styling — teal/navy palette from the studio photo.
st.markdown(
    """
    <style>
      :root { --pb-teal:#2DD4BF; --pb-teal-dim:#1f8f83; --pb-navy:#16263f; }
      .block-container {padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1400px;}
      /* subtle teal glow background */
      [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(900px 500px at 12% -8%, rgba(45,212,191,0.10), transparent 60%),
            radial-gradient(800px 500px at 100% 0%, rgba(22,38,63,0.55), transparent 55%);
      }
      /* metric cards */
      [data-testid="stMetric"] {
          background: linear-gradient(180deg, rgba(45,212,191,0.08), rgba(18,40,46,0.55));
          border: 1px solid rgba(45,212,191,0.22);
          border-radius: 14px; padding: 14px 16px;
      }
      [data-testid="stMetricValue"] {font-size: 1.55rem; color: #F2FBFA;}
      [data-testid="stMetricLabel"] {color:#9FD6CE;}
      /* tabs */
      div[data-baseweb="tab-list"] {gap: 6px; border-bottom: 1px solid rgba(45,212,191,0.15);}
      button[data-baseweb="tab"] {border-radius: 10px 10px 0 0;}
      button[data-baseweb="tab"][aria-selected="true"] {
          background: rgba(45,212,191,0.12); color: var(--pb-teal);
      }
      /* post cards */
      div[data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: 14px;
          transition: border-color .15s ease, transform .15s ease;
      }
      div[data-testid="stVerticalBlockBorderWrapper"]:hover {
          border-color: rgba(45,212,191,0.45);
      }
      /* primary buttons */
      .stButton button, .stFormSubmitButton button {border-radius: 10px;}
      /* PulseBoard hero */
      .pb-hero {display:flex; align-items:center; justify-content:center; gap:16px;
          margin: 7vh 0 4px; text-align:left;}
      .pb-logo {
          font-size: 30px; width:54px; height:54px; display:flex; align-items:center;
          justify-content:center; border-radius:14px;
          background: linear-gradient(135deg, #2DD4BF, #16263f);
          box-shadow: 0 0 24px rgba(45,212,191,0.35);
      }
      .pb-title {font-size: 1.9rem; font-weight: 800; letter-spacing:-0.5px;
          background: linear-gradient(90deg,#FFFFFF,#7FE8DC);
          -webkit-background-clip:text; -webkit-text-fill-color:transparent; line-height:1.1;}
      .pb-sub {color:#9FD6CE; font-size:0.9rem; margin-top:2px;}
      .pb-badge {color:#0B1A1E; background:var(--pb-teal); font-weight:700;
          font-size:0.72rem; padding:3px 10px; border-radius:999px; margin-left:6px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _hero_background_css() -> str:
    """If a photo exists in assets/, embed it as a blurred full-page backdrop."""
    import base64
    import glob
    import os

    candidates = []
    for ext in ("jpg", "jpeg", "png", "webp"):
        candidates += glob.glob(os.path.join("assets", f"*.{ext}"))
    if not candidates:
        return ""
    path = sorted(candidates)[0]
    mime = "jpeg" if path.lower().endswith(("jpg", "jpeg")) else \
        ("png" if path.lower().endswith("png") else "webp")
    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except OSError:
        return ""
    return f"""
    <style>
      [data-testid="stAppViewContainer"]::before {{
          content: ""; position: fixed; inset: 0; z-index: -2;
          background: url('data:image/{mime};base64,{b64}') center 16% / cover no-repeat;
          filter: blur(8px) brightness(0.55) saturate(1.08);
          transform: scale(1.06);
      }}
      /* teal wash over the photo so text stays crisp but photo shows through */
      [data-testid="stAppViewContainer"]::after {{
          content: ""; position: fixed; inset: 0; z-index: -1;
          background: linear-gradient(180deg, rgba(11,26,30,0.55), rgba(11,26,30,0.86));
      }}
    </style>
    """


def human(n) -> str:
    """Compact number: 1234567 -> '1.2M'."""
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    if pd.isna(n):
        return "—"
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n / div:.1f}{unit}"
    return f"{int(n):,}"

# Auto-reload the page hourly (3600s). Streamlit reruns the script on refresh,
# re-reading the SQLite snapshots written by the scheduler.
st.markdown(
    "<meta http-equiv='refresh' content='3600'>", unsafe_allow_html=True
)

try:
    init_db()
except Exception as _db_err:  # noqa: BLE001
    st.error("⚠️ Could not connect to the database.")
    st.code(str(_db_err))
    st.markdown(
        "**Likely fix:** check the `TURSO_DATABASE_URL` secret is your real "
        "Turso URL (looks like `libsql://yourdb-you.turso.io`) with **no `...`** "
        "placeholder, and that `TURSO_AUTH_TOKEN` is the full token. "
        "Edit them under **app → Settings → Secrets**, then reboot."
    )
    st.stop()


def _check_password() -> bool:
    """Dormant password gate. Open unless an APP_PASSWORD secret is set.
    To lock the app: add  APP_PASSWORD = "yourpass"  in Streamlit secrets."""
    try:
        pw = st.secrets["APP_PASSWORD"] if "APP_PASSWORD" in st.secrets else None
    except Exception:  # noqa: BLE001
        pw = None
    if not pw:
        return True  # no password configured -> open access
    if st.session_state.get("pb_auth"):
        return True
    st.markdown("## 🔒 PulseBoard")
    entered = st.text_input("Password", type="password")
    if entered == pw:
        st.session_state["pb_auth"] = True
        st.rerun()
    elif entered:
        st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()


@st.cache_data(ttl=300)
def load_latest() -> pd.DataFrame:
    return latest_metrics()


@st.cache_data(ttl=300)
def load_history() -> pd.DataFrame:
    return all_history()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_image(url: str):
    """Download image bytes server-side (bypasses Instagram CDN hotlink blocks).
    Cached for an hour so it doesn't re-download on every rerun."""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def detect_platform(text: str) -> str | None:
    """Guess the platform from a pasted handle or URL."""
    t = text.lower()
    if "youtube.com" in t or "youtu.be" in t:
        return "youtube"
    if "instagram.com" in t:
        return "instagram"
    return None


def normalize_target(platform: str, text: str) -> str:
    """Turn user input into what the collector expects."""
    t = text.strip()
    if platform == "instagram":
        # accept @handle, full URL, or bare username -> bare username
        if "instagram.com" in t:
            t = t.rstrip("/").split("/")[-1] or t.rstrip("/").split("/")[-2]
        return t.lstrip("@")
    # youtube: collector takes a channel URL or @handle
    if t.startswith("@") or t.startswith("http"):
        return t
    return f"https://www.youtube.com/@{t}"


st.markdown(_hero_background_css(), unsafe_allow_html=True)
st.markdown(
    """
    <div class="pb-hero">
      <div class="pb-logo">⚡</div>
      <div>
        <div class="pb-title">PulseBoard <span class="pb-badge">LIVE</span></div>
        <div class="pb-sub">The pulse of every post · Instagram &amp; YouTube performance
        — built for <b>Vaibhav Sisinty</b></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown(
    "<div style='text-align:center; color:#8FB8B2; font-size:0.86rem; "
    "max-width:760px; margin:0 auto 8px;'>Search any public Instagram username or "
    "YouTube channel to fetch its last 10 days of posts — views, likes, comments, "
    "engagement &amp; growth. Share counts aren't exposed publicly, so they're not "
    "shown.</div>",
    unsafe_allow_html=True,
)

# ---------------- SEARCH BAR ----------------
with st.form("search", clear_on_submit=False):
    sc1, sc2, sc3 = st.columns([3, 1, 1])
    query = sc1.text_input(
        "🔍 Search a page",
        placeholder="e.g. natgeo  ·  @mkbhd  ·  https://www.youtube.com/@MrBeast",
        label_visibility="collapsed",
    )
    plat_choice = sc2.selectbox("Platform", ["Auto", "Instagram", "YouTube"],
                                label_visibility="collapsed")
    go = sc3.form_submit_button("Fetch", use_container_width=True)

if go and query.strip():
    platform = {"Instagram": "instagram", "YouTube": "youtube"}.get(plat_choice)
    if platform is None:  # Auto
        platform = detect_platform(query)
    if platform is None:
        st.error(
            "Couldn't tell if that's Instagram or YouTube. Pick a platform from "
            "the dropdown, or paste a full profile/channel URL."
        )
    else:
        target = normalize_target(platform, query)
        from collect import collect_target
        with st.spinner(f"Fetching {platform}: {target} …"):
            try:
                res = collect_target(platform, target)
                if res["posts"] == 0:
                    st.warning(
                        f"No public posts found for '{target}'. Check the spelling, "
                        "or the account may be private / have no recent posts."
                    )
                else:
                    st.success(
                        f"Fetched {res['posts']} posts for "
                        f"{', '.join(res['accounts']) or target}"
                    )
                    # Show ONLY this freshly searched account.
                    st.session_state["focus_accounts"] = res["accounts"]
                    st.session_state["focus_query"] = (platform, target)
                    st.cache_data.clear()
            except Exception as e:  # noqa: BLE001
                st.error(f"Fetch failed: {e}")

focus = st.session_state.get("focus_accounts")

# ---------------- WELCOME / EMPTY STATE ----------------
if not focus:
    st.info("👆 Search a public Instagram username or YouTube channel to begin.")
    e1, e2, e3 = st.columns(3)
    e1.markdown("**Instagram**\n\n`natgeo` · `nasa`")
    e2.markdown("**YouTube**\n\n`@mkbhd` · `@MrBeast`")
    e3.markdown("**Or paste a URL**\n\n`youtube.com/@channel`")
    st.caption(
        "You'll get the last 10 days of posts: views, likes, comments, post date, "
        "engagement rate, and growth over time. (Share counts aren't public, so "
        "they're not shown.)"
    )
    st.stop()

# ---- focus bar + controls ----
fc1, fc2, fc3 = st.columns([3, 1, 1])
fc1.success(f"📍 Showing: **{', '.join(focus)}**")
if fc2.button("🔄 Refresh data", use_container_width=True):
    fq = st.session_state.get("focus_query")
    if fq:
        from collect import collect_target
        with st.spinner("Refreshing…"):
            collect_target(*fq)
        st.cache_data.clear()
        st.rerun()
if fc3.button("✖ New search", use_container_width=True):
    st.session_state.pop("focus_accounts", None)
    st.session_state.pop("focus_query", None)
    st.cache_data.clear()
    st.rerun()

latest = load_latest()
latest = latest[latest["account"].isin(focus)]  # only the searched account

if latest.empty:
    st.warning("No data for that page yet — try **Refresh data** or search again.")
    st.stop()

table = per_post_table(latest)
summary = account_summary(latest)

# ---- top-line KPIs (compact, responsive) ----
total_views = int(table["views"].fillna(0).sum())
total_likes = int(table["likes"].fillna(0).sum())
total_comments = int(table["comments"].fillna(0).sum())
eng = table["engagement_rate_%"].dropna()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Posts", len(table))
k2.metric("Views", human(total_views))
k3.metric("Likes", human(total_likes))
k4.metric("Comments", human(total_comments))
k5.metric("Avg engagement", f"{eng.mean():.2f}%" if not eng.empty else "—")

NUM_COLS = {
    "views": st.column_config.NumberColumn("views", format="%d"),
    "likes": st.column_config.NumberColumn("likes", format="%d"),
    "comments": st.column_config.NumberColumn("comments", format="%d"),
    "url": st.column_config.LinkColumn("link", display_text="open"),
    "published_at": st.column_config.DatetimeColumn("posted", format="YYYY-MM-DD HH:mm"),
    "engagement_rate_%": st.column_config.NumberColumn("eng %", format="%.2f"),
}

tab_feed, tab_table, tab_trends, tab_movers, tab_ai = st.tabs(
    ["📋 Posts", "📊 Table", "📈 Trends", "🚀 Movers", "🧠 AI Analysis"]
)

TYPE_ICON = {"video": "🎬", "short": "▶️", "reel": "🎬", "clips": "🎬",
             "image": "🖼️", "sidecar": "🖼️", "post": "📷"}


def render_card(row) -> None:
    """One post as a card: thumbnail + its individual metrics."""
    with st.container(border=True):
        c_img, c_meta = st.columns([1, 3.5])
        with c_img:
            thumb = row.get("thumbnail")
            img_bytes = fetch_image(thumb) if isinstance(thumb, str) and thumb.startswith("http") else None
            if img_bytes:
                st.image(img_bytes, use_container_width=True)
            else:
                st.markdown(
                    f"<div style='font-size:46px;text-align:center'>"
                    f"{TYPE_ICON.get(row.get('post_type'), '📄')}</div>",
                    unsafe_allow_html=True,
                )
        with c_meta:
            posted = row.get("published_at")
            posted_str = posted.strftime("%b %d, %Y · %H:%M") if pd.notna(posted) else "—"
            title = (row.get("title") or "(no caption)").strip().replace("\n", " ")
            st.markdown(f"**{title[:160]}**")
            st.caption(f"{TYPE_ICON.get(row.get('post_type'),'')} {row.get('post_type')}  ·  🗓 {posted_str}")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("👁 Views", human(row.get("views")))
            m2.metric("❤️ Likes", human(row.get("likes")))
            m3.metric("💬 Comments", human(row.get("comments")))
            er = row.get("engagement_rate_%")
            m4.metric("📊 Eng", f"{er:.2f}%" if pd.notna(er) else "—")
            if isinstance(row.get("url"), str):
                st.markdown(f"[↗ Open post]({row['url']})")


# ---------------- POST FEED (per-post, last 10 days) ----------------
with tab_feed:
    f1, f2 = st.columns([2, 2])
    plat = f1.radio("Platform", ["All", "instagram", "youtube"],
                    horizontal=True, key="feed_plat")
    sort_by = f2.selectbox(
        "Sort by", ["Newest", "Most views", "Most likes", "Most engagement"],
        key="feed_sort",
    )
    view = table if plat == "All" else table[table["platform"] == plat]
    sort_map = {
        "Newest": ("published_at", False),
        "Most views": ("views", False),
        "Most likes": ("likes", False),
        "Most engagement": ("engagement_rate_%", False),
    }
    col, asc = sort_map[sort_by]
    view = view.sort_values(col, ascending=asc, na_position="last")

    st.caption(f"{len(view)} posts in the last 10 days")
    for _, row in view.iterrows():
        render_card(row)

# ---------------- TABLE ----------------
with tab_table:
    st.caption("Click a column header to sort.")
    st.dataframe(
        table[["platform", "account", "post_type", "published_at",
               "views", "likes", "comments", "engagement_rate_%", "url"]],
        use_container_width=True, hide_index=True, column_config=NUM_COLS,
    )

# ---------------- TRENDS ----------------
with tab_trends:
    hist_all = load_history()
    hist_focus = hist_all[hist_all["account"].isin(focus)]
    snap_counts = hist_focus.groupby("post_id").size().to_dict()
    # Order posts so those WITH trend history (>=2 snapshots) appear first.
    rows = sorted(
        table.itertuples(),
        key=lambda r: (snap_counts.get(r.id, 0) >= 2, snap_counts.get(r.id, 0)),
        reverse=True,
    )
    labels = {}
    for r in rows:
        n = snap_counts.get(r.id, 0)
        tag = "📈 " if n >= 2 else "🆕 "
        labels[f"{tag}[{r.platform}] {(r.title or '(no title)')[:65]}"] = r.id

    have_history = sum(1 for n in snap_counts.values() if n >= 2)
    if have_history:
        st.caption(f"📈 = has trend data ({have_history} posts) · 🆕 = needs one more collection")
    if labels:
        pick = st.selectbox("Pick a post", list(labels.keys()))
        hist = snapshot_history(labels[pick])
        if len(hist) >= 2:
            hist["captured_at"] = pd.to_datetime(hist["captured_at"], utc=True)
            long = hist.melt("captured_at", ["views", "likes", "comments"],
                             var_name="metric", value_name="value").dropna(subset=["value"])
            st.plotly_chart(
                px.line(long, x="captured_at", y="value", color="metric",
                        markers=True, title="Metric growth over time"),
                use_container_width=True,
            )
        else:
            st.info(
                "This post has only one snapshot so far. Trend lines appear once "
                "it's been collected twice — the tracker re-checks every few hours "
                "automatically, or hit **🔄 Refresh data** above to add a point now."
            )

# ---------------- MOVERS ----------------
with tab_movers:
    hist = load_history()
    hist = hist[hist["account"].isin(focus)]  # only the searched account
    # Compare across the whole tracked period (first vs latest snapshot),
    # so movers show as soon as any post has 2+ snapshots.
    gro = growth_since(hist, hours=24 * 14)
    if gro.empty:
        st.info(
            "Movers compares two snapshots of the same post. This account has "
            "been collected once so far — once it's collected again (every few "
            "hours, or hit **🔄 Refresh data**), the biggest gainers show here."
        )
    else:
        st.caption("Views & likes gained over the tracked period")
        st.dataframe(
            gro.head(20), use_container_width=True, hide_index=True,
            column_config={
                "views_gained": st.column_config.NumberColumn(format="%d"),
                "likes_gained": st.column_config.NumberColumn(format="%d"),
            },
        )

# ---------------- AI ANALYSIS ----------------
with tab_ai:
    st.caption("Written growth analysis from the exact figures above (OpenRouter).")
    if st.button("Generate analysis"):
        try:
            from analysis import llm_insights
            top = table.sort_values("views", ascending=False).head(10)[
                ["platform", "account", "title", "views", "likes",
                 "comments", "engagement_rate_%"]
            ]
            with st.spinner("Analyzing with OpenRouter…"):
                st.markdown(llm_insights(summary, top))
        except Exception as e:  # noqa: BLE001
            st.error(f"AI analysis unavailable: {e}")
            st.caption("Add your full OPENROUTER_API_KEY to .env to enable this.")
