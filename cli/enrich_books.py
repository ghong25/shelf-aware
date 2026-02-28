#!/usr/bin/env python3
"""Merge genre + page-count classifications into books JSON.

This script takes the original books JSON on stdin and a classifications file
(produced by a Claude subagent) as an argument, merges them, and writes the
enriched books JSON to stdout.

Usage:
    cat books.json | python enrich_books.py classifications.json > enriched_books.json

The classifications file should be a JSON array of objects, one per book,
matched by book index (same order as books in the input):
    [
      {"title": "...", "genres": ["Literary Fiction", "Classics"], "page_count": 320},
      ...
    ]
"""

import json
import sys


GENRE_TAXONOMY = [
    "Literary Fiction",
    "Science Fiction",
    "Fantasy",
    "Mystery/Thriller",
    "Romance",
    "Historical Fiction",
    "Horror",
    "Biography/Memoir",
    "Self-Help",
    "Science/Nature",
    "Philosophy",
    "Poetry",
    "History",
    "Psychology",
    "Business/Economics",
    "True Crime",
    "Humor",
    "Religion/Spirituality",
    "Young Adult",
    "Classics",
    "Graphic Novel",
    "Politics/Social Science",
    "Art/Design",
    "Essays",
    "Travel",
    "Parenting/Family",
    "Health/Wellness",
]

VALID_GENRES = set(GENRE_TAXONOMY)


def merge(data: dict, classifications: list[dict]) -> dict:
    """Merge classifications into books by index position."""
    books = data.get("books", [])
    if not books or not classifications:
        return data

    enriched = 0

    for idx, clf in enumerate(classifications):
        if idx >= len(books):
            break

        # Genres — validate against taxonomy
        genres = clf.get("genres", [])
        if genres and isinstance(genres, list):
            valid = [g for g in genres if isinstance(g, str) and g.strip() in VALID_GENRES]
            if valid:
                books[idx]["genres"] = valid
                enriched += 1

        # Page count
        page_count = clf.get("page_count")
        if page_count and isinstance(page_count, (int, float)) and page_count > 0:
            books[idx]["page_count"] = int(page_count)

    print(f"Enriched {enriched}/{len(books)} books with genres.", file=sys.stderr)
    return data


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: cat books.json | python enrich_books.py classifications.json",
            file=sys.stderr,
        )
        sys.exit(1)

    clf_path = sys.argv[1]

    # Read books from stdin
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid books JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    # Read classifications from file
    try:
        with open(clf_path) as f:
            classifications = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(f"ERROR: Failed to read classifications: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(classifications, list):
        print("ERROR: Classifications must be a JSON array.", file=sys.stderr)
        sys.exit(1)

    data = merge(data, classifications)

    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
