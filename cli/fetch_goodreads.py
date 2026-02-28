#!/usr/bin/env python3
"""Fetch a user's Goodreads reading history from RSS."""

import csv
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx


def _load_dotenv() -> None:
    """Load .env file from project root into os.environ (simple parser)."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes if present
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            os.environ.setdefault(key, value)


_load_dotenv()

# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

# Slim CSV columns — the minimal set AI agents need for analysis
SLIM_COLUMNS = ["title", "author", "user_rating", "average_rating", "date_read", "year_published"]


def extract_user_id(url_or_id: str) -> str:
    """Pull numeric Goodreads user ID from a URL or bare ID string.

    Supports formats like:
      - 12345
      - https://www.goodreads.com/user/show/12345
      - https://www.goodreads.com/user/show/12345-username
      - https://goodreads.com/review/list/12345?shelf=read
      - goodreads.com/user/show/12345-some-name
    """
    url_or_id = url_or_id.strip()

    # Bare numeric ID
    if re.fullmatch(r"\d+", url_or_id):
        return url_or_id

    # URL patterns — grab the first numeric segment after a path component
    match = re.search(r"goodreads\.com/(?:user/show|review/list(?:_rss)?)/(\d+)", url_or_id)
    if match:
        return match.group(1)

    # Fallback: find any leading digits in the string
    match = re.search(r"(\d+)", url_or_id)
    if match:
        return match.group(1)

    raise ValueError(f"Could not extract a Goodreads user ID from: {url_or_id!r}")


def _text(item: ET.Element, tag: str) -> str:
    """Safely get text content of a child element."""
    el = item.find(tag)
    if el is not None and el.text:
        return el.text.strip()
    return ""


def _int_or_none(value: str) -> int | None:
    """Parse an int, returning None on failure."""
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _float_or_zero(value: str) -> float:
    """Parse a float, returning 0.0 on failure."""
    value = value.strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def detect_private_profile(response_text: str) -> bool:
    """Check whether an RSS response indicates a private profile.

    Returns True if the response has no <item> elements and no channel title,
    which indicates the feed is inaccessible.
    """
    if not response_text or not response_text.strip():
        return True

    # If there's valid XML but zero items and no channel title, treat as private
    try:
        root = ET.fromstring(response_text)
        channel = root.find("channel")
        if channel is None:
            return True
        items = channel.findall("item")
        title = _text(channel, "title")
        if not items and not title:
            return True
    except ET.ParseError:
        return True

    return False


def fetch_rss_page(
    user_id: str, page: int, client: httpx.Client, shelf: str = "read"
) -> tuple[list[dict], str]:
    """Fetch one page of a user's read-shelf RSS and parse book data.

    Returns (books, user_name) where user_name is extracted from the
    channel title on the first call.
    """
    url = (
        f"https://www.goodreads.com/review/list_rss/{user_id}"
        f"?shelf={shelf}&page={page}"
    )

    response = client.get(url, timeout=15.0)
    response.raise_for_status()

    text = response.text
    if detect_private_profile(text):
        raise PermissionError(
            f"Goodreads profile {user_id} appears to be private or invalid."
        )

    root = ET.fromstring(text)
    channel = root.find("channel")
    if channel is None:
        return [], ""

    # Extract user_name from channel title (format: "username's bookshelf: read")
    user_name = ""
    channel_title = _text(channel, "title")
    if channel_title:
        match = re.match(r"^(.+?)(?:'s|\u2019s) bookshelf", channel_title)
        if match:
            user_name = match.group(1).strip()

    books: list[dict] = []
    for item in channel.findall("item"):
        title = _text(item, "title")
        author = _text(item, "author_name")
        isbn = _text(item, "isbn")
        book_id = _text(item, "book_id")
        user_rating = _int_or_none(_text(item, "user_rating")) or 0
        average_rating = _float_or_zero(_text(item, "average_rating"))
        date_read = _text(item, "user_read_at")
        date_added = _text(item, "user_date_added")
        shelves = _text(item, "user_shelves")
        year_published = _int_or_none(_text(item, "book_published"))

        # Cover URL: prefer large image, fall back to regular
        cover_url = _text(item, "book_large_image_url") or _text(
            item, "book_image_url"
        )

        books.append(
            {
                "title": title,
                "author": author,
                "isbn": isbn,
                "book_id": book_id,
                "user_rating": user_rating,
                "average_rating": average_rating,
                "date_read": date_read,
                "date_added": date_added,
                "shelves": shelves,
                "year_published": year_published,
                "cover_url": cover_url,
            }
        )

    return books, user_name


def fetch_all_books(user_id: str) -> tuple[list[dict], str]:
    """Paginate through all pages of a user's read shelf.

    Uses GOODREADS_COOKIE env var for authenticated access to private profiles.
    Tries the #ALL# shelf first (works better with auth), falls back to 'read'.

    Returns (deduplicated_books, user_name).
    """
    all_books: list[dict] = []
    seen_ids: set[str] = set()
    user_name = ""

    headers = {"User-Agent": "shelf-aware/0.1 (book-stats CLI)"}
    cookie = os.environ.get("GOODREADS_COOKIE", "")
    if cookie:
        headers["Cookie"] = cookie
        print("Using authenticated session.", file=sys.stderr)

    # Try read shelf first; fall back to #ALL# with auth
    shelves_to_try = (["read", "%23ALL%23"] if cookie else ["read"])

    with httpx.Client(
        headers=headers,
        follow_redirects=True,
    ) as client:
        for shelf in shelves_to_try:
            page = 1
            all_books = []
            seen_ids = set()
            user_name = ""

            try:
                while True:
                    print(f"Fetching RSS page {page} (shelf={shelf})...", file=sys.stderr)
                    books, name = fetch_rss_page(user_id, page, client, shelf=shelf)

                    if name and not user_name:
                        user_name = name

                    if not books:
                        break

                    for book in books:
                        bid = book["book_id"]
                        if bid and bid not in seen_ids:
                            seen_ids.add(bid)
                            all_books.append(book)

                    page += 1
                    time.sleep(1)  # polite delay between pages

            except (PermissionError, httpx.HTTPStatusError) as exc:
                if shelf != shelves_to_try[-1]:
                    print(f"Shelf {shelf} failed ({exc}), trying next...", file=sys.stderr)
                    continue
                raise

            if all_books:
                break
            elif shelf != shelves_to_try[-1]:
                print(f"No books on shelf {shelf}, trying next...", file=sys.stderr)

    print(
        f"Fetched {len(all_books)} unique books across {page - 1} page(s).",
        file=sys.stderr,
    )
    return all_books, user_name


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python fetch_goodreads.py <goodreads_user_id_or_url>",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_input = sys.argv[1]

    try:
        user_id = extract_user_id(raw_input)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Resolved user ID: {user_id}", file=sys.stderr)

    # Fetch reading history from RSS
    try:
        books, user_name = fetch_all_books(user_id)
    except PermissionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"HTTP error fetching RSS: {exc}", file=sys.stderr)
        sys.exit(1)

    if not books:
        print("No books found on the read shelf.", file=sys.stderr)
        sys.exit(1)

    # Save to data/<name_id>/
    project_root = Path(__file__).resolve().parent.parent
    safe_name = re.sub(r"[^\w-]", "_", user_name.lower()).strip("_") if user_name else "unknown"
    dir_name = f"{safe_name}_{user_id}"
    data_dir = project_root / "data" / dir_name
    data_dir.mkdir(parents=True, exist_ok=True)

    # Full JSON (for web frontend / storage)
    output = {
        "user_id": user_id,
        "user_name": user_name,
        "fetch_date": datetime.now(timezone.utc).isoformat(),
        "book_count": len(books),
        "books": books,
    }
    json_path = data_dir / "books.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Slim CSV (for AI agents)
    csv_path = data_dir / "books.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SLIM_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for book in books:
            # Normalize date_read to just YYYY-MM-DD
            row = {k: book.get(k, "") for k in SLIM_COLUMNS}
            if row["date_read"]:
                try:
                    dt = datetime.strptime(row["date_read"], "%a, %d %b %Y %H:%M:%S %z")
                    row["date_read"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            writer.writerow(row)

    print(f"\nSaved {len(books)} books to:", file=sys.stderr)
    print(f"  {json_path} (full)", file=sys.stderr)
    print(f"  {csv_path} (slim for AI)", file=sys.stderr)


if __name__ == "__main__":
    main()
