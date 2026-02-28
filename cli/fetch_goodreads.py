#!/usr/bin/env python3
"""Fetch a user's Goodreads reading history from RSS and enrich via OpenLibrary."""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------------
# Genre taxonomy
# ---------------------------------------------------------------------------

GENRE_TAXONOMY = [
    "Literary Fiction",
    "Science Fiction",
    "Fantasy",
    "Mystery/Thriller",
    "Romance",
    "Horror",
    "Historical Fiction",
    "Contemporary Fiction",
    "Young Adult",
    "Children's",
    "Biography/Memoir",
    "History",
    "Science",
    "Philosophy",
    "Psychology",
    "Self-Help",
    "Business",
    "Poetry",
    "Art/Design",
    "Travel",
    "Religion/Spirituality",
    "Politics",
    "True Crime",
    "Humor",
    "Other",
]

# Maps lowercase keyword fragments found in OpenLibrary subjects to taxonomy.
# Order matters: first match wins, so put more specific patterns before general.
_GENRE_KEYWORDS: list[tuple[str, str]] = [
    # Fiction sub-genres
    ("science fiction", "Science Fiction"),
    ("sci-fi", "Science Fiction"),
    ("scifi", "Science Fiction"),
    ("fantasy", "Fantasy"),
    ("mystery", "Mystery/Thriller"),
    ("thriller", "Mystery/Thriller"),
    ("suspense", "Mystery/Thriller"),
    ("detective", "Mystery/Thriller"),
    ("crime fiction", "Mystery/Thriller"),
    ("romance", "Romance"),
    ("love stories", "Romance"),
    ("horror", "Horror"),
    ("gothic", "Horror"),
    ("historical fiction", "Historical Fiction"),
    ("young adult", "Young Adult"),
    ("ya ", "Young Adult"),
    ("teen", "Young Adult"),
    ("children", "Children's"),
    ("juvenile", "Children's"),
    ("picture book", "Children's"),
    ("literary fiction", "Literary Fiction"),
    ("contemporary fiction", "Contemporary Fiction"),
    ("general fiction", "Contemporary Fiction"),
    ("fiction", "Literary Fiction"),  # generic fallback for fiction

    # Non-fiction
    ("true crime", "True Crime"),
    ("biography", "Biography/Memoir"),
    ("memoir", "Biography/Memoir"),
    ("autobiography", "Biography/Memoir"),
    ("history", "History"),
    ("historical", "History"),
    ("science", "Science"),
    ("physics", "Science"),
    ("biology", "Science"),
    ("chemistry", "Science"),
    ("mathematics", "Science"),
    ("astronomy", "Science"),
    ("evolution", "Science"),
    ("neuroscience", "Science"),
    ("philosophy", "Philosophy"),
    ("ethics", "Philosophy"),
    ("psychology", "Psychology"),
    ("mental health", "Psychology"),
    ("psychiatry", "Psychology"),
    ("self-help", "Self-Help"),
    ("self help", "Self-Help"),
    ("personal development", "Self-Help"),
    ("motivation", "Self-Help"),
    ("productivity", "Self-Help"),
    ("business", "Business"),
    ("economics", "Business"),
    ("management", "Business"),
    ("entrepreneurship", "Business"),
    ("finance", "Business"),
    ("investing", "Business"),
    ("marketing", "Business"),
    ("poetry", "Poetry"),
    ("poems", "Poetry"),
    ("art", "Art/Design"),
    ("design", "Art/Design"),
    ("photography", "Art/Design"),
    ("architecture", "Art/Design"),
    ("travel", "Travel"),
    ("religion", "Religion/Spirituality"),
    ("spiritual", "Religion/Spirituality"),
    ("theology", "Religion/Spirituality"),
    ("buddhism", "Religion/Spirituality"),
    ("christianity", "Religion/Spirituality"),
    ("islam", "Religion/Spirituality"),
    ("meditation", "Religion/Spirituality"),
    ("politics", "Politics"),
    ("political", "Politics"),
    ("government", "Politics"),
    ("humor", "Humor"),
    ("comedy", "Humor"),
    ("satire", "Humor"),
    ("funny", "Humor"),
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


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

    Returns True if the response has no <item> elements or contains error
    indicators suggesting the profile is private.
    """
    if not response_text or not response_text.strip():
        return True

    # Look for common error signals
    lower = response_text.lower()
    if "private" in lower and "profile" in lower:
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
    user_id: str, page: int, client: httpx.Client
) -> tuple[list[dict], str]:
    """Fetch one page of a user's read-shelf RSS and parse book data.

    Returns (books, user_name) where user_name is extracted from the
    channel title on the first call.
    """
    url = (
        f"https://www.goodreads.com/review/list_rss/{user_id}"
        f"?shelf=read&page={page}"
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

    Returns (deduplicated_books, user_name).
    """
    all_books: list[dict] = []
    seen_ids: set[str] = set()
    user_name = ""
    page = 1

    with httpx.Client(
        headers={"User-Agent": "shelf-aware/0.1 (book-stats CLI)"},
        follow_redirects=True,
    ) as client:
        while True:
            print(f"Fetching RSS page {page}...", file=sys.stderr)
            books, name = fetch_rss_page(user_id, page, client)

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

    print(
        f"Fetched {len(all_books)} unique books across {page - 1} page(s).",
        file=sys.stderr,
    )
    return all_books, user_name


def normalize_genres(subjects: list[str]) -> list[str]:
    """Map raw OpenLibrary subject strings to a clean genre taxonomy.

    Returns a deduplicated list of matched genre categories, preserving the
    order in which they were first matched.
    """
    matched: list[str] = []
    seen: set[str] = set()

    for subject in subjects:
        lower = subject.lower()
        for keyword, genre in _GENRE_KEYWORDS:
            if keyword in lower and genre not in seen:
                seen.add(genre)
                matched.append(genre)
                break  # one match per subject string

    return matched if matched else ["Other"]


def enrich_with_openlibrary(
    books: list[dict],
) -> tuple[list[dict], list[str]]:
    """Enrich books with genre and page-count data from OpenLibrary.

    Returns (enriched_books, errors).
    """
    errors: list[str] = []
    books_with_isbn = [(i, b) for i, b in enumerate(books) if b.get("isbn")]
    total = len(books_with_isbn)

    if total == 0:
        print("No books with ISBNs to enrich.", file=sys.stderr)
        for book in books:
            book.setdefault("genres", ["Other"])
            book.setdefault("page_count", None)
        return books, errors

    print(f"Enriching {total} books via OpenLibrary...", file=sys.stderr)

    with httpx.Client(
        headers={"User-Agent": "shelf-aware/0.1 (book-stats CLI)"},
        follow_redirects=True,
        timeout=5.0,
    ) as client:
        for idx, (pos, book) in enumerate(books_with_isbn):
            isbn = book["isbn"]
            url = f"https://openlibrary.org/isbn/{isbn}.json"
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_subjects = data.get("subjects", [])
                    book["genres"] = normalize_genres(raw_subjects)
                    book["page_count"] = data.get("number_of_pages")
                elif resp.status_code == 404:
                    book["genres"] = ["Other"]
                    book["page_count"] = None
                else:
                    msg = (
                        f"OpenLibrary returned {resp.status_code} for "
                        f"ISBN {isbn} ({book['title']})"
                    )
                    errors.append(msg)
                    print(f"  Warning: {msg}", file=sys.stderr)
                    book["genres"] = ["Other"]
                    book["page_count"] = None
            except httpx.HTTPError as exc:
                msg = f"HTTP error enriching ISBN {isbn} ({book['title']}): {exc}"
                errors.append(msg)
                print(f"  Warning: {msg}", file=sys.stderr)
                book["genres"] = ["Other"]
                book["page_count"] = None

            # Progress indicator every 10 books
            if (idx + 1) % 10 == 0 or (idx + 1) == total:
                print(
                    f"  Enriched {idx + 1}/{total} books.",
                    file=sys.stderr,
                )

            time.sleep(0.5)  # polite delay between requests

    # Fill defaults for books without ISBNs
    for book in books:
        book.setdefault("genres", ["Other"])
        book.setdefault("page_count", None)

    return books, errors


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

    # Enrich with OpenLibrary data
    books, errors = enrich_with_openlibrary(books)

    # Build output
    output = {
        "user_id": user_id,
        "user_name": user_name,
        "fetch_date": datetime.now(timezone.utc).isoformat(),
        "book_count": len(books),
        "books": books,
        "errors": errors,
    }

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    print(
        f"\nDone. {len(books)} books exported with {len(errors)} error(s).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
