#!/usr/bin/env python3
"""Build the Blaugust blog directory and recent-post data from one CSV file.

The authoritative source is data/blogs.csv. The directory output is generated
immediately from that file. Unless --directory-only is supplied, eligible feeds
are checked and the latest 20 posts are rebuilt as well.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import html
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

try:
    import feedparser
    import requests
    from dateutil import parser as date_parser
except ModuleNotFoundError:  # Directory-only validation needs no feed packages.
    feedparser = None
    requests = None
    date_parser = None

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data" / "blogs.csv"
CACHE_PATH = ROOT / "data" / "feed-cache.json"
DOCS_DIR = ROOT / "docs"
LATEST_JSON_PATH = DOCS_DIR / "latest-posts.json"
LATEST_JS_PATH = DOCS_DIR / "latest-posts-data.js"
DIRECTORY_JSON_PATH = DOCS_DIR / "blog-directory.json"
DIRECTORY_JS_PATH = DOCS_DIR / "blog-directory-data.js"

MAX_POSTS = int(os.getenv("MAX_POSTS", "20"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "18"))
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "10"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "25"))
MAX_FEED_BYTES = int(os.getenv("MAX_FEED_BYTES", str(6 * 1024 * 1024)))
USER_AGENT = os.getenv(
    "USER_AGENT",
    "BlaugustDirectory/2.0 (+https://www.containsmoderateperil.com/blaugust-blogroll)",
)

REQUIRED_COLUMNS = {
    "name",
    "site_url",
    "feed_url",
    "language",
    "directory_group",
    "status",
    "show_in_directory",
    "include_in_latest",
    "notes",
}
VALID_DIRECTORY_GROUPS = {"alphabetical", "other-languages"}
TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off", ""}
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class BlogRecord:
    name: str
    site_url: str
    feed_url: str
    language: str
    directory_group: str
    status: str
    show_in_directory: bool
    include_in_latest: bool
    notes: str


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
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def parse_bool(value: str, *, row_number: int, field: str) -> bool:
    normalised = str(value or "").strip().casefold()
    if normalised in TRUE_VALUES:
        return True
    if normalised in FALSE_VALUES:
        return False
    raise ValueError(
        f"Row {row_number}: {field} must be yes/no (received {value!r})."
    )


def validate_http_url(value: str, *, row_number: int, field: str) -> str:
    url = clean_url(value)
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"Row {row_number}: invalid {field}: {value!r}")
    return url


def load_master() -> list[BlogRecord]:
    if not MASTER_PATH.exists():
        raise FileNotFoundError(f"Missing master data file: {MASTER_PATH}")

    records: list[BlogRecord] = []
    seen_feeds: dict[str, int] = {}

    with MASTER_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        actual = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - actual
        if missing:
            raise ValueError(
                "The master CSV is missing columns: " + ", ".join(sorted(missing))
            )

        for row_number, row in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in row.values()):
                continue

            name = clean_text(row.get("name"))
            if not name:
                raise ValueError(f"Row {row_number}: name is required.")

            site_url = validate_http_url(
                row.get("site_url", ""), row_number=row_number, field="site_url"
            )
            feed_url = validate_http_url(
                row.get("feed_url", ""), row_number=row_number, field="feed_url"
            )
            if feed_url in seen_feeds:
                first = seen_feeds[feed_url]
                raise ValueError(
                    f"Row {row_number}: duplicate feed_url; first used on row {first}."
                )
            seen_feeds[feed_url] = row_number

            directory_group = str(row.get("directory_group") or "").strip().casefold()
            if directory_group not in VALID_DIRECTORY_GROUPS:
                raise ValueError(
                    f"Row {row_number}: directory_group must be alphabetical or "
                    f"other-languages (received {directory_group!r})."
                )

            records.append(
                BlogRecord(
                    name=name,
                    site_url=site_url,
                    feed_url=feed_url,
                    language=clean_text(row.get("language")) or "Unspecified",
                    directory_group=directory_group,
                    status=clean_text(row.get("status")) or "included",
                    show_in_directory=parse_bool(
                        row.get("show_in_directory", ""),
                        row_number=row_number,
                        field="show_in_directory",
                    ),
                    include_in_latest=parse_bool(
                        row.get("include_in_latest", ""),
                        row_number=row_number,
                        field="include_in_latest",
                    ),
                    notes=clean_text(row.get("notes")),
                )
            )

    if not records:
        raise RuntimeError("The master CSV contains no blog records.")
    return records


def directory_initial(record: BlogRecord) -> str:
    if record.directory_group == "other-languages":
        return "other-languages"

    for character in record.name:
        if not character.isalnum():
            continue
        if character.isdigit():
            return "0-9"
        folded = unicodedata.normalize("NFKD", character)
        for candidate in folded:
            upper = candidate.upper()
            if "A" <= upper <= "Z":
                return upper
        break
    return "0-9"


def safe_js_json(data: dict[str, Any]) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        text.replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def write_directory(records: list[BlogRecord], generated_at: str) -> dict[str, Any]:
    visible = [record for record in records if record.show_in_directory]
    visible.sort(
        key=lambda record: (
            1 if record.directory_group == "other-languages" else 0,
            unicodedata.normalize("NFKD", record.name).casefold(),
        )
    )

    blogs = [
        {
            "name": record.name,
            "site_url": record.site_url,
            "feed_url": record.feed_url,
            "language": record.language,
            "directory_group": record.directory_group,
            "initial": directory_initial(record),
        }
        for record in visible
    ]
    output: dict[str, Any] = {
        "generated_at": generated_at,
        "blog_count": len(blogs),
        "other_language_count": sum(
            1 for blog in blogs if blog["directory_group"] == "other-languages"
        ),
        "blogs": blogs,
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DIRECTORY_JSON_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    DIRECTORY_JS_PATH.write_text(
        "window.__blaugustBlogDirectoryData=" + safe_js_json(output) + ";\n"
        "if(typeof window.__cmpRenderBlaugustBlogDirectory==='function'){"
        "window.__cmpRenderBlaugustBlogDirectory(window.__blaugustBlogDirectoryData);}\n",
        encoding="utf-8",
    )
    return output


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
                "Accept": (
                    "application/atom+xml, application/rss+xml, application/xml, "
                    "text/xml, */*;q=0.5"
                ),
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
    except Exception as exc:
        return FeedResult(
            source=source,
            post=None,
            error=f"{type(exc).__name__}: {exc}",
        )


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


def write_recent_posts(records: list[BlogRecord], checked_at: str) -> int:
    if feedparser is None or requests is None or date_parser is None:
        raise RuntimeError(
            "Feed dependencies are not installed. Run: pip install -r requirements.txt"
        )

    sources = [
        FeedSource(
            title=record.name,
            feed_url=record.feed_url,
            website_url=record.site_url,
        )
        for record in records
        if record.include_in_latest
    ]
    if not sources:
        raise RuntimeError("No blogs are enabled for the latest-post panel.")

    started = time.monotonic()
    cache = load_cache()
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
            failures.append(
                {
                    "feed": feed_url,
                    "blog": result.source.title,
                    "error": result.error or "unknown error",
                }
            )

    valid_feeds = {source.feed_url for source in sources}
    cache = {key: value for key, value in cache.items() if key in valid_feeds}

    sorted_posts = sorted(
        posts_by_feed.values(),
        key=lambda post: iso_to_datetime(post.published),
        reverse=True,
    )
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

    output: dict[str, Any] = {
        "generated_at": checked_at,
        "feed_count": len(sources),
        "successful_feeds": successes,
        "failed_feeds": len(failures),
        "post_count": len(newest_posts),
        "posts": [asdict(post) for post in newest_posts],
    }

    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LATEST_JSON_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LATEST_JS_PATH.write_text(
        "window.__blaugustRecentPostsData=" + safe_js_json(output) + ";\n"
        "if(typeof window.__cmpRenderBlaugustRecentPosts==='function'){"
        "window.__cmpRenderBlaugustRecentPosts(window.__blaugustRecentPostsData);}\n",
        encoding="utf-8",
    )

    duration = round(time.monotonic() - started, 1)
    print(
        f"Checked {len(sources)} feeds in {duration}s: "
        f"{successes} succeeded, {len(failures)} failed."
    )
    print(f"Wrote {len(newest_posts)} recent posts to {LATEST_JSON_PATH.relative_to(ROOT)}.")
    if failures:
        print("Feed failures (cached results retained where available):", file=sys.stderr)
        for failure in sorted(failures, key=lambda item: item["blog"].casefold()):
            print(f"- {failure['blog']}: {failure['error']}", file=sys.stderr)
    return 0 if newest_posts else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--directory-only",
        action="store_true",
        help="Validate blogs.csv and rebuild only the directory data.",
    )
    args = parser.parse_args()

    records = load_master()
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    directory = write_directory(records, generated_at)
    print(
        f"Validated {len(records)} master rows and wrote "
        f"{directory['blog_count']} visible directory entries "
        f"({directory['other_language_count']} in Other Languages)."
    )

    if args.directory_only:
        return 0
    return write_recent_posts(records, generated_at)


if __name__ == "__main__":
    raise SystemExit(main())
