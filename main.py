"""Scrape with Apify, then summarize the results with OpenRouter.

Usage:
    python main.py "https://example.com"
    python main.py "https://example.com" --actor apify/website-content-crawler

By default it runs Apify's Website Content Crawler, collects the scraped
text, and asks an OpenRouter model for an accurate summary.
"""
from __future__ import annotations

import argparse
import json
import sys

from clients import get_apify, get_openrouter, OPENROUTER_MODEL, run_dataset_id

DEFAULT_ACTOR = "apify/website-content-crawler"


def scrape(url: str, actor: str, max_pages: int = 5) -> list[dict]:
    """Run an Apify actor and return its dataset items."""
    client = get_apify()
    run_input = {
        "startUrls": [{"url": url}],
        "maxCrawlPages": max_pages,
    }
    print(f"[apify] running actor '{actor}' on {url} ...", file=sys.stderr)
    run = client.actor(actor).call(run_input=run_input)
    items = list(client.dataset(run_dataset_id(run)).iterate_items())
    print(f"[apify] collected {len(items)} item(s)", file=sys.stderr)
    return items


def _extract_text(items: list[dict], char_limit: int = 24000) -> str:
    """Pull readable text out of scraped items, truncated for the prompt."""
    chunks: list[str] = []
    for it in items:
        for key in ("text", "markdown", "content", "body", "description"):
            val = it.get(key)
            if isinstance(val, str) and val.strip():
                chunks.append(val.strip())
                break
        else:
            chunks.append(json.dumps(it, ensure_ascii=False))
    joined = "\n\n---\n\n".join(chunks)
    return joined[:char_limit]


def summarize(text: str) -> str:
    """Summarize scraped text via OpenRouter. Prioritizes accuracy."""
    client = get_openrouter()
    print(f"[openrouter] summarizing with {OPENROUTER_MODEL} ...", file=sys.stderr)
    resp = client.chat.completions.create(
        model=OPENROUTER_MODEL,
        temperature=0,  # deterministic, factual
        messages=[
            {
                "role": "system",
                "content": (
                    "You summarize scraped web content. Be accurate and concise. "
                    "Only state facts present in the provided text. If something is "
                    "unclear or missing, say so rather than guessing."
                ),
            },
            {"role": "user", "content": f"Summarize the following:\n\n{text}"},
        ],
    )
    return resp.choices[0].message.content or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape a URL then summarize it.")
    parser.add_argument("url", help="URL to scrape")
    parser.add_argument("--actor", default=DEFAULT_ACTOR, help="Apify actor id")
    parser.add_argument("--max-pages", type=int, default=5)
    args = parser.parse_args()

    items = scrape(args.url, args.actor, args.max_pages)
    if not items:
        print("No content scraped.", file=sys.stderr)
        sys.exit(1)

    text = _extract_text(items)
    summary = summarize(text)

    print("\n===== SUMMARY =====\n")
    print(summary)


if __name__ == "__main__":
    main()
