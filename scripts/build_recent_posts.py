#!/usr/bin/env python3
"""Build a compact recent-posts feed from a Feedly OPML export.

The script checks each feed, keeps one newest dated post per blog, preserves the
last successful result when a feed temporarily fails, and writes files suitable
for GitHub Pages and a Squarespace widget.
"""

from __future__ import annotations

import calendar
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parents[1]
OPML_PATH = ROOT / "data" / "feedly.opml"
OVERRIDES_PATH = ROOT / "data" / "overrides.json"
CACHE_PATH = ROOT / "data" / "feed-cache.json"
DOCS_DIR = ROOT / "docs"
JSON_PATH = DOCS_DIR / "latest-posts.json"
JS_PATH = DOCS_DIR / "latest-posts-data.js"

MAX_POSTS = int(os.getenv("MAX_POSTS", "20"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "18"))
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "25"))
MAX_FEED_BYTES = int(os.getenv("MAX_FEED_BYTES", str(6 * 1024 * 1024)))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "BlaugustRecentPosts/1.0 (+https://www.containsmoderateperil.com/blaugust-blogroll)",
)

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class FeedSource:
    title: str
    feed_url: str
    website_url: str


@dataclass
class Post:
    blog_title: str
    blog_url: str
    feed_url: str
    post_title: str
    post_url: str
    published: str


@dataclass
class FeedResult:
    source: FeedSource
    post: Post | None
    error: str | None = None


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def clean_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    # Fragments are not useful for canonical post or homepage links.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def derive_homepage(feed_url: str) -> str:
    parts = urlsplit(feed_url)
    if not parts.scheme or not parts.netloc:
        return feed_url
    return f"{parts.scheme}://{parts.netloc}/"


def load_sources() -> list[FeedSource]:
    if not OPML_PATH.exists():
        raise FileNotFoundError(f"Missing OPML file: {OPML_PATH}")

    overrides: dict[str, dict[str, str]] = {}
    if OVERRIDES_PATH.exists():
        overrides = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))

    root = ET.parse(OPML_PATH).getroot()
    sources: list[FeedSource] = []
    seen: set[str] = set()

    for outline in root.findall(".//outline"):
        feed_url = clean_url(outline.attrib.get("xmlUrl"))
        if not feed_url or feed_url in seen:
            continue
        seen.add(feed_url)

        title = clean_text(outline.attrib.get("title") or outline.attrib.get("text"))
        website_url = clean_url(outline.attrib.get("htmlUrl")) or derive_homepage(feed_url)

        correction = overrides.get(feed_url, {})
        title = clean_text(correction.get("title", title)) or website_url
        website_url = clean_url(correction.get("website_url", website_url))

        sources.append(FeedSource(title=title, feed_url=feed_url, website_url=website_url))

    if not sources:
        raise RuntimeError("No RSS or Atom subscriptions were found in the OPML file.")
    return sources


def parse_struct_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return None


def parse_entry_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = parse_struct_time(entry.get(key))
        if parsed:
            return parsed

    for key in ("published", "updated", "created", "date"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            parsed = date_parser.parse(str(raw))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def entry_link(entry: Any) -> str:
    direct = clean_url(entry.get("link"))
    if direct:
        return direct
    for link in entry.get("links", []):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return clean_url(link["href"])
    return ""


def fetch_latest(source: FeedSource) -> FeedResult:
    try:
        response = requests.get(
            source.feed_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml, */*;q=0.5",
            },
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=True,
        )
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError(f"feed exceeds {MAX_FEED_BYTES} bytes")

        parsed = feedparser.parse(response.content)
        if not parsed.entries:
            detail = getattr(parsed, "bozo_exception", "no entries")
            raise ValueError(f"no usable entries ({detail})")

        now = datetime.now(timezone.utc)
        newest: tuple[datetime, Post] | None = None

        for entry in parsed.entries[:20]:
            title = clean_text(entry.get("title"))
            link = entry_link(entry)
            published = parse_entry_date(entry)
            if not title or not link or not published:
                continue
            if published < datetime(1990, 1, 1, tzinfo=timezone.utc):
                continue
            if published > now + timedelta(days=1):
                continue

            post = Post(
                blog_title=source.title,
                blog_url=source.website_url,
                feed_url=source.feed_url,
                post_title=title,
                post_url=link,
                published=published.isoformat().replace("+00:00", "Z"),
            )
            if newest is None or published > newest[0]:
                newest = (published, post)

        if newest is None:
            raise ValueError("entries were present but none had a usable title, link and date")
        return FeedResult(source=source, post=newest[1])
    except Exception as exc:  # A single faulty feed must not stop the whole build.
        return FeedResult(source=source, post=None, error=f"{type(exc).__name__}: {exc}")


def load_cache() -> dict[str, dict[str, Any]]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def iso_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def safe_js_json(data: dict[str, Any]) -> str:
    # Avoid accidental script-token or Unicode line-separator problems.
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def main() -> int:
    started = time.monotonic()
    sources = load_sources()
    cache = load_cache()
    checked_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    results: list[FeedResult] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(fetch_latest, source): source for source in sources}
        for future in as_completed(future_map):
            results.append(future.result())

    successes = 0
    failures: list[dict[str, str]] = []
    posts_by_feed: dict[str, Post] = {}

    for result in results:
        feed_url = result.source.feed_url
        if result.post:
            successes += 1
            posts_by_feed[feed_url] = result.post
            cache[feed_url] = {
                "post": asdict(result.post),
                "last_success": checked_at,
                "last_checked": checked_at,
                "last_error": None,
            }
        else:
            old = cache.get(feed_url, {})
            old_post = old.get("post")
            if isinstance(old_post, dict):
                try:
                    posts_by_feed[feed_url] = Post(**old_post)
                except TypeError:
                    pass
            cache[feed_url] = {
                **old,
                "last_checked": checked_at,
                "last_error": result.error,
            }
            failures.append({"feed": feed_url, "blog": result.source.title, "error": result.error or "unknown error"})

    # Remove cache entries for feeds no longer present in the OPML.
    valid_feeds = {source.feed_url for source in sources}
    cache = {key: value for key, value in cache.items() if key in valid_feeds}

    # Sort newest-first and prevent duplicate article URLs from appearing twice.
    sorted_posts = sorted(posts_by_feed.values(), key=lambda post: iso_to_datetime(post.published), reverse=True)
    newest_posts: list[Post] = []
    seen_post_urls: set[str] = set()
    for post in sorted_posts:
        canonical = post.post_url.rstrip("/")
        if canonical in seen_post_urls:
            continue
        seen_post_urls.add(canonical)
        newest_posts.append(post)
        if len(newest_posts) >= MAX_POSTS:
            break

    duration = round(time.monotonic() - started, 1)
    output: dict[str, Any] = {
        "generated_at": checked_at,
        "feed_count": len(sources),
        "successful_feeds": successes,
        "failed_feeds": len(failures),
        "post_count": len(newest_posts),
        "posts": [asdict(post) for post in newest_posts],
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    JSON_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    JS_PATH.write_text(
        "window.__blaugustRecentPostsData=" + safe_js_json(output) + ";\n"
        "if(typeof window.__cmpRenderBlaugustRecentPosts==='function'){"
        "window.__cmpRenderBlaugustRecentPosts(window.__blaugustRecentPostsData);}\n",
        encoding="utf-8",
    )

    print(f"Checked {len(sources)} feeds in {duration}s: {successes} succeeded, {len(failures)} failed.")
    print(f"Wrote {len(newest_posts)} recent posts to {JSON_PATH.relative_to(ROOT)}.")
    if failures:
        print("Feed failures (cached results retained where available):", file=sys.stderr)
        for failure in sorted(failures, key=lambda item: item["blog"].casefold()):
            print(f"- {failure['blog']}: {failure['error']}", file=sys.stderr)
    return 0 if newest_posts else 1


if __name__ == "__main__":
    raise SystemExit(main())
