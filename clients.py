"""API client layer: Apify (scraping) + OpenRouter (summarization).

Credentials are loaded from .env. Nothing is hardcoded here.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv
from apify_client import ApifyClient
from openai import OpenAI

load_dotenv()

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _require(value: str, name: str) -> str:
    if not value or "REPLACE" in value:
        raise RuntimeError(
            f"{name} is missing or still a placeholder. Set it in .env."
        )
    return value


def get_apify() -> ApifyClient:
    """Return an authenticated Apify client."""
    return ApifyClient(_require(APIFY_TOKEN, "APIFY_TOKEN"))


def get_openrouter() -> OpenAI:
    """Return an OpenAI-compatible client pointed at OpenRouter."""
    return OpenAI(
        api_key=_require(OPENROUTER_API_KEY, "OPENROUTER_API_KEY"),
        base_url=OPENROUTER_BASE_URL,
    )


def run_dataset_id(run) -> str:
    """Get the default dataset id from an actor run (dict or pydantic Run)."""
    if isinstance(run, dict):
        return run["defaultDatasetId"]
    return run.default_dataset_id


def run_cost_usd(run) -> float | None:
    """Best-effort USD cost of a run, for credit tracking."""
    if isinstance(run, dict):
        return run.get("usageTotalUsd")
    return getattr(run, "usage_total_usd", None)


def check_apify() -> dict:
    """Verify the Apify token by fetching the authenticated user."""
    me = get_apify().user("me").get()
    # Newer apify-client returns a pydantic model; fall back to dict access.
    username = getattr(me, "username", None) or (me.get("username") if hasattr(me, "get") else None)
    plan = getattr(me, "plan", None) or (me.get("plan") if hasattr(me, "get") else None)
    return {"ok": True, "username": username, "plan": plan}


def check_openrouter() -> dict:
    """Verify the OpenRouter key with a minimal completion."""
    client = get_openrouter()
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=5,
    )
    return {"ok": True, "model": resp.model, "reply": resp.choices[0].message.content}
