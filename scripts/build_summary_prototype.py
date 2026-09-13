#!/usr/bin/env python3
"""Build an isolated AI-summary prototype from docs/latest-posts.json.

This script does not alter the live recent-post feed data. It reads the existing
20-post output, fetches readable article text for posts that are not already
cached, asks the Gemini API for a short neutral summary, and writes separate
prototype JSON/JavaScript files.

Environment variables:
    GEMINI_API_KEY        Required for creating new summaries.
    GEMINI_MODEL          Defaults to gemini-3.6-flash.
    SUMMARY_MAX_NEW       Maximum uncached posts to summarise in one run (20).
    SUMMARY_EXCERPT_CHARS Maximum extracted article characters sent to Gemini.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from readability import Document

ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "docs" / "latest-posts.json"
CACHE_PATH = ROOT / "data" / "summary-cache.json"
OUTPUT_JSON_PATH = ROOT / "docs" / "latest-posts-summaries.json"
OUTPUT_JS_PATH = ROOT / "docs" / "latest-posts-summaries-data.js"

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
MAX_NEW = max(0, int(os.getenv("SUMMARY_MAX_NEW", "20")))
MAX_EXCERPT_CHARS = max(1000, int(os.getenv("SUMMARY_EXCERPT_CHARS", "6000")))
MAX_ARTICLE_BYTES = max(250_000, int(os.getenv("SUMMARY_MAX_ARTICLE_BYTES", str(3 * 1024 * 1024))))
CONNECT_TIMEOUT = float(os.getenv("SUMMARY_CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = float(os.getenv("SUMMARY_READ_TIMEOUT", "25"))
USER_AGENT = os.getenv(
    "SUMMARY_USER_AGENT",
    "BlaugustSummaryPrototype/0.1 (+https://www.containsmoderateperil.com/blaugust-blogroll)",
)

SPACE_RE = re.compile(r"\s+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_url(value: str) -> str:
    parts = urlsplit(str(value or "").strip())
    if not parts.scheme or not parts.netloc:
        return str(value or "").strip()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def clean_text(value: Any) -> str:
    return SPACE_RE.sub(" ", html.unescape(str(value or ""))).strip()


def safe_js_json(data: dict[str, Any]) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def extract_readable_text(url: str) -> str:
    response = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.2",
        },
        timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        allow_redirects=True,
    )
    response.raise_for_status()

    content_type = (response.headers.get("Content-Type") or "").lower()
    if "html" not in content_type and "xhtml" not in content_type:
        raise ValueError(f"unsupported content type: {content_type or 'unknown'}")
    if len(response.content) > MAX_ARTICLE_BYTES:
        raise ValueError(f"article exceeds {MAX_ARTICLE_BYTES} bytes")

    response.encoding = response.apparent_encoding or response.encoding
    source_html = response.text

    readable_html = ""
    try:
        readable_html = Document(source_html).summary(html_partial=True)
    except Exception:
        readable_html = ""

    soup = BeautifulSoup(readable_html or source_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
        tag.decompose()

    text = clean_text(soup.get_text(" "))
    if len(text) < 250 and readable_html:
        soup = BeautifulSoup(source_html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer", "aside"]):
            tag.decompose()
        text = clean_text(soup.get_text(" "))

    if len(text) < 200:
        raise ValueError("not enough readable article text")
    return text[:MAX_EXCERPT_CHARS]


def gemini_summary(
    *,
    api_key: str,
    blog_title: str,
    post_title: str,
    article_text: str,
) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent"
    )
    prompt = f"""You are writing a discovery blurb for a community blogroll.

Write exactly one neutral English sentence of 18 to 30 words summarising the
article below. Describe what the article is about, not whether it is good.
Do not use phrases such as "this post", "this article", "the author discusses",
or "AI-generated". Do not invent facts, motives, or conclusions absent from the
provided text. Preserve important names and titles. If the source text is not
English, summarise it in English.

BLOG: {blog_title}
TITLE: {post_title}

ARTICLE TEXT:
{article_text}
"""

    response = requests.post(
        endpoint,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 100,
                "candidateCount": 1,
            },
        },
        timeout=(CONNECT_TIMEOUT, 60),
    )
    response.raise_for_status()
    payload = response.json()

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(str(part.get("text") or "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Gemini response did not contain summary text") from exc

    summary = clean_text(text).strip(" \"'")
    if not summary:
        raise ValueError("Gemini returned an empty summary")
    if len(summary) > 500:
        raise ValueError("Gemini returned an unexpectedly long summary")
    return summary


def write_outputs(source: dict[str, Any], posts: list[dict[str, Any]], generated_at: str) -> None:
    summarised = sum(1 for post in posts if post.get("summary"))
    output = {
        "generated_at": generated_at,
        "source_generated_at": source.get("generated_at"),
        "summary_model": MODEL,
        "post_count": len(posts),
        "summary_count": summarised,
        "posts": posts,
    }

    OUTPUT_JSON_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    OUTPUT_JS_PATH.write_text(
        "window.__blaugustRecentPostSummariesData=" + safe_js_json(output) + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Do not fetch articles or call Gemini; rebuild prototype output from existing cache.",
    )
    args = parser.parse_args()

    source = load_json(INPUT_PATH, {})
    source_posts = source.get("posts") if isinstance(source, dict) else None
    if not isinstance(source_posts, list) or not source_posts:
        raise RuntimeError(f"No posts found in {INPUT_PATH.relative_to(ROOT)}")

    cache = load_json(CACHE_PATH, {})
    if not isinstance(cache, dict):
        cache = {}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    can_create = bool(api_key) and not args.cache_only
    generated_at = utc_now()
    created_this_run = 0
    output_posts: list[dict[str, Any]] = []
    failures: list[str] = []

    for source_post in source_posts:
        if not isinstance(source_post, dict):
            continue
        post = dict(source_post)
        post_url = str(post.get("post_url") or "").strip()
        key = canonical_url(post_url)
        cached = cache.get(key) if key else None

        summary: str | None = None
        if isinstance(cached, dict):
            cached_summary = clean_text(cached.get("summary"))
            if cached_summary:
                summary = cached_summary

        if summary is None and can_create and created_this_run < MAX_NEW and post_url:
            try:
                article_text = extract_readable_text(post_url)
                summary = gemini_summary(
                    api_key=api_key,
                    blog_title=clean_text(post.get("blog_title")),
                    post_title=clean_text(post.get("post_title")),
                    article_text=article_text,
                )
                cache[key] = {
                    "post_url": post_url,
                    "post_title": clean_text(post.get("post_title")),
                    "blog_title": clean_text(post.get("blog_title")),
                    "summary": summary,
                    "model": MODEL,
                    "created_at": generated_at,
                    "source_chars": len(article_text),
                }
                created_this_run += 1
                time.sleep(0.75)
            except Exception as exc:
                failures.append(
                    f"{clean_text(post.get('blog_title'))} — "
                    f"{clean_text(post.get('post_title'))}: {type(exc).__name__}: {exc}"
                )

        post["summary"] = summary
        output_posts.append(post)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_outputs(source, output_posts, generated_at)

    print(
        f"Wrote {len(output_posts)} prototype posts; "
        f"{sum(1 for post in output_posts if post.get('summary'))} have summaries."
    )
    if not can_create:
        if args.cache_only:
            print("Cache-only mode: no article fetching or Gemini calls were attempted.")
        else:
            print("GEMINI_API_KEY is not set: existing cached summaries were used only.")
    else:
        print(f"Created {created_this_run} new summaries with {MODEL}.")

    if failures:
        print("Summary failures (prototype continues without those summaries):", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
