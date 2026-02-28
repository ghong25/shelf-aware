#!/usr/bin/env python3
"""Compute hard comparison analytics between two readers.

Reads JSON from stdin:
{
    "books_a": [...], "books_b": [...],
    "stats_a": {...}, "stats_b": {...},
    "user_a": "name", "user_b": "name"
}

Outputs comparison stats JSON to stdout.
"""

import json
import sys
from collections import Counter


def _normalize_title(title):
    """Lowercase, strip whitespace/punctuation for fuzzy matching."""
    if not title:
        return ""
    return "".join(c for c in title.lower() if c.isalnum() or c == " ").strip()


def _book_key(book):
    """Return a matching key for a book — prefer book_id, fall back to normalized title+author."""
    bid = book.get("book_id")
    if bid and str(bid).strip():
        return f"id:{bid}"
    title = _normalize_title(book.get("title", ""))
    author = _normalize_title(book.get("author", ""))
    return f"ta:{title}|{author}"


def compute_shared_shelf(books_a, books_b):
    """Find books both people have read. Returns shared books with both ratings."""
    index_b = {}
    for b in books_b:
        index_b[_book_key(b)] = b

    shared = []
    keys_a = set()
    for a in books_a:
        key = _book_key(a)
        if key in keys_a:
            continue
        keys_a.add(key)
        if key in index_b:
            b = index_b[key]
            shared.append({
                "title": a.get("title") or b.get("title"),
                "author": a.get("author") or b.get("author"),
                "rating_a": a.get("user_rating", 0),
                "rating_b": b.get("user_rating", 0),
            })

    only_a = len(keys_a) - len(shared)
    only_b = len(set(_book_key(b) for b in books_b)) - len(shared)

    return {
        "shared_count": len(shared),
        "only_a_count": only_a,
        "only_b_count": only_b,
        "shared_books": shared,
        "venn_data": {
            "only_a": only_a,
            "shared": len(shared),
            "only_b": only_b,
        },
    }


def compute_the_rift(shared_books):
    """Find biggest rating disagreements from shared books."""
    disagreements = []
    for book in shared_books:
        ra = book["rating_a"]
        rb = book["rating_b"]
        if ra and ra > 0 and rb and rb > 0:
            diff = abs(ra - rb)
            if diff > 0:
                disagreements.append({
                    "title": book["title"],
                    "author": book["author"],
                    "rating_a": ra,
                    "rating_b": rb,
                    "difference": diff,
                })

    disagreements.sort(key=lambda x: x["difference"], reverse=True)

    agreements = [b for b in shared_books
                  if b["rating_a"] and b["rating_a"] > 0
                  and b["rating_b"] and b["rating_b"] > 0
                  and b["rating_a"] == b["rating_b"]]

    return {
        "biggest_rifts": disagreements[:5],
        "total_disagreements": len(disagreements),
        "perfect_agreements": len(agreements),
        "agreement_examples": [{"title": b["title"], "rating": b["rating_a"]} for b in agreements[:3]],
    }


def compute_pace_vs_patience(stats_a, stats_b, user_a, user_b):
    """Side-by-side pace and page length comparison."""
    pace_a = stats_a.get("reading_pace", {})
    pace_b = stats_b.get("reading_pace", {})
    span_a = stats_a.get("attention_span", {})
    span_b = stats_b.get("attention_span", {})

    bpy_a = pace_a.get("books_per_year", 0)
    bpy_b = pace_b.get("books_per_year", 0)
    avg_pages_a = span_a.get("avg_pages", 0)
    avg_pages_b = span_b.get("avg_pages", 0)

    # Who reads more vs who reads longer
    volume_winner = user_a if bpy_a > bpy_b else user_b if bpy_b > bpy_a else "tie"
    length_winner = user_a if avg_pages_a > avg_pages_b else user_b if avg_pages_b > avg_pages_a else "tie"

    return {
        "user_a": {
            "name": user_a,
            "books_per_year": round(bpy_a, 1),
            "avg_pages": round(avg_pages_a),
            "label": span_a.get("label", "Unknown"),
        },
        "user_b": {
            "name": user_b,
            "books_per_year": round(bpy_b, 1),
            "avg_pages": round(avg_pages_b),
            "label": span_b.get("label", "Unknown"),
        },
        "volume_winner": volume_winner,
        "length_winner": length_winner,
    }


def compute_genre_overlap(stats_a, stats_b):
    """Build dual-layer radar chart data from both genre radars."""
    radar_a = stats_a.get("genre_radar", {})
    radar_b = stats_b.get("genre_radar", {})
    counts_a = radar_a.get("genre_counts", {})
    counts_b = radar_b.get("genre_counts", {})

    # Union of all genres, sorted by combined count
    all_genres = set(counts_a.keys()) | set(counts_b.keys())
    genre_totals = {g: counts_a.get(g, 0) + counts_b.get(g, 0) for g in all_genres}
    top_genres = sorted(genre_totals, key=genre_totals.get, reverse=True)[:10]

    values_a = [counts_a.get(g, 0) for g in top_genres]
    values_b = [counts_b.get(g, 0) for g in top_genres]

    # Overlap = genres both have, divergence = genres only one has
    shared_genres = [g for g in top_genres if counts_a.get(g, 0) > 0 and counts_b.get(g, 0) > 0]
    only_a_genres = [g for g in top_genres if counts_a.get(g, 0) > 0 and counts_b.get(g, 0) == 0]
    only_b_genres = [g for g in top_genres if counts_b.get(g, 0) > 0 and counts_a.get(g, 0) == 0]

    return {
        "dual_chart_data": {
            "labels": top_genres,
            "values_a": values_a,
            "values_b": values_b,
        },
        "shared_genres": shared_genres,
        "only_a_genres": only_a_genres,
        "only_b_genres": only_b_genres,
    }


def compute_decades_alignment(stats_a, stats_b):
    """Dual bar chart of publication decades."""
    eras_a = stats_a.get("reading_eras", {})
    eras_b = stats_b.get("reading_eras", {})
    chart_a = eras_a.get("chart_data", {})
    chart_b = eras_b.get("chart_data", {})

    labels_a = chart_a.get("labels", [])
    labels_b = chart_b.get("labels", [])
    vals_a = dict(zip(labels_a, chart_a.get("values", [])))
    vals_b = dict(zip(labels_b, chart_b.get("values", [])))

    all_decades = sorted(set(labels_a) | set(labels_b), key=lambda l: int(l[:-1]))
    values_a = [vals_a.get(d, 0) for d in all_decades]
    values_b = [vals_b.get(d, 0) for d in all_decades]

    dom_a = eras_a.get("dominant_era")
    dom_b = eras_b.get("dominant_era")
    same_era = dom_a == dom_b if dom_a and dom_b else None

    return {
        "dual_chart_data": {
            "labels": all_decades,
            "values_a": values_a,
            "values_b": values_b,
        },
        "dominant_a": dom_a,
        "dominant_b": dom_b,
        "same_era": same_era,
    }


def compute_rating_clash(stats_a, stats_b, user_a, user_b):
    """Compare rating personalities."""
    hh_a = stats_a.get("hater_hype", {})
    hh_b = stats_b.get("hater_hype", {})
    rd_a = stats_a.get("rating_distribution", {})
    rd_b = stats_b.get("rating_distribution", {})

    return {
        "user_a": {
            "name": user_a,
            "label": hh_a.get("label", "Unknown"),
            "mean_diff": hh_a.get("mean_diff", 0),
            "average_rating": rd_a.get("average", 0),
            "pct_5_star": rd_a.get("pct_5_star", 0),
        },
        "user_b": {
            "name": user_b,
            "label": hh_b.get("label", "Unknown"),
            "mean_diff": hh_b.get("mean_diff", 0),
            "average_rating": rd_b.get("average", 0),
            "pct_5_star": rd_b.get("pct_5_star", 0),
        },
        "same_style": hh_a.get("label") == hh_b.get("label"),
    }


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON input: {exc}"}), file=sys.stderr)
        sys.exit(1)

    books_a = data.get("books_a", [])
    books_b = data.get("books_b", [])
    stats_a = data.get("stats_a", {})
    stats_b = data.get("stats_b", {})
    user_a = data.get("user_a", "Reader A")
    user_b = data.get("user_b", "Reader B")

    shared = compute_shared_shelf(books_a, books_b)

    result = {
        "shared_shelf": shared,
        "the_rift": compute_the_rift(shared["shared_books"]),
        "pace_vs_patience": compute_pace_vs_patience(stats_a, stats_b, user_a, user_b),
        "genre_overlap": compute_genre_overlap(stats_a, stats_b),
        "decades_alignment": compute_decades_alignment(stats_a, stats_b),
        "rating_clash": compute_rating_clash(stats_a, stats_b, user_a, user_b),
    }

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
