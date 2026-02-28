#!/usr/bin/env python3
"""CLI script that reads book JSON from stdin and outputs stats JSON to stdout.

Usage:
    cat books.json | python compute_stats.py > stats.json
"""

import json
import sys
import statistics
from collections import Counter
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%a, %d %b %Y %H:%M:%S %z",   # RFC 2822 (Goodreads RSS)
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
]


def parse_date(date_str):
    """Try multiple date formats and return a naive datetime or None."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Strip timezone info so all comparisons use naive datetimes
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def safe_float(value, default=None):
    """Convert a value to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=None):
    """Convert a value to int, returning *default* on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# 1. Hater vs Hype Index
# ---------------------------------------------------------------------------

def compute_hater_hype_index(books):
    """Compare user ratings to average ratings to determine rating tendency."""
    points = []
    diffs = []

    for b in books:
        user_r = safe_float(b.get("user_rating"))
        avg_r = safe_float(b.get("average_rating"))
        if user_r is None or avg_r is None or user_r == 0:
            continue
        diff = user_r - avg_r
        diffs.append(diff)
        points.append({
            "x": round(avg_r, 2),
            "y": round(user_r, 2),
            "title": b.get("title", ""),
        })

    if not diffs:
        return {
            "mean_diff": 0.0,
            "label": "Fair Judge",
            "scatter_data": {"points": []},
            "total_rated": 0,
        }

    mean_diff = statistics.mean(diffs)

    if mean_diff < -0.5:
        label = "Contrarian Critic"
    elif mean_diff > 0.5:
        label = "Hype Beast"
    else:
        label = "Fair Judge"

    return {
        "mean_diff": round(mean_diff, 4),
        "label": label,
        "scatter_data": {"points": points},
        "total_rated": len(diffs),
    }


# ---------------------------------------------------------------------------
# 2. Reading Eras Timeline
# ---------------------------------------------------------------------------

def compute_reading_eras(books):
    """Group books by publication decade."""
    decade_counts = Counter()

    for b in books:
        year = safe_int(b.get("year_published"))
        if year is None or year < 0:
            continue
        decade_start = (year // 10) * 10
        label = f"{decade_start}s"
        decade_counts[label] += 1

    if not decade_counts:
        return {
            "chart_data": {"labels": [], "values": []},
            "dominant_era": None,
            "era_range": None,
        }

    # Sort labels chronologically
    sorted_labels = sorted(decade_counts.keys(), key=lambda l: int(l[:-1]))
    sorted_values = [decade_counts[l] for l in sorted_labels]

    dominant_era = max(decade_counts, key=decade_counts.get)
    era_range = f"{sorted_labels[0]} - {sorted_labels[-1]}" if len(sorted_labels) > 1 else sorted_labels[0]

    return {
        "chart_data": {"labels": sorted_labels, "values": sorted_values},
        "dominant_era": dominant_era,
        "era_range": era_range,
    }


# ---------------------------------------------------------------------------
# 3. Attention Span Metric
# ---------------------------------------------------------------------------

_PAGE_BUCKETS = [
    ("0-100", 0, 100),
    ("101-200", 101, 200),
    ("201-300", 201, 300),
    ("301-400", 301, 400),
    ("401-500", 401, 500),
    ("501-700", 501, 700),
    ("700+", 701, float("inf")),
]


def compute_attention_span(books):
    """Analyse page-count distribution."""
    pages_list = []

    for b in books:
        pc = safe_int(b.get("page_count"))
        if pc is not None and pc > 0:
            pages_list.append(pc)

    bucket_counts = [0] * len(_PAGE_BUCKETS)
    for p in pages_list:
        for idx, (_, lo, hi) in enumerate(_PAGE_BUCKETS):
            if lo <= p <= hi:
                bucket_counts[idx] += 1
                break

    if not pages_list:
        return {
            "avg_pages": 0.0,
            "median_pages": 0.0,
            "label": "Sprint Reader",
            "chart_data": {
                "labels": [b[0] for b in _PAGE_BUCKETS],
                "values": bucket_counts,
            },
        }

    avg_pages = statistics.mean(pages_list)
    median_pages = statistics.median(pages_list)

    if avg_pages < 250:
        label = "Sprint Reader"
    elif avg_pages <= 400:
        label = "Marathoner"
    else:
        label = "Ultramarathoner"

    return {
        "avg_pages": round(avg_pages, 2),
        "median_pages": round(median_pages, 2),
        "label": label,
        "chart_data": {
            "labels": [b[0] for b in _PAGE_BUCKETS],
            "values": bucket_counts,
        },
    }


# ---------------------------------------------------------------------------
# 4. Genre Radar
# ---------------------------------------------------------------------------

def compute_genre_radar(books):
    """Count books per genre and compute diversity score."""
    genre_counter = Counter()
    total_books = len(books)

    for b in books:
        genres = b.get("genres")
        if not genres or not isinstance(genres, list):
            continue
        for g in genres:
            if isinstance(g, str) and g.strip():
                genre_counter[g.strip()] += 1

    if not genre_counter:
        return {
            "chart_data": {"labels": [], "values": []},
            "diversity_score": 0.0,
            "top_genre": None,
            "genre_counts": {},
        }

    top_8 = genre_counter.most_common(8)
    diversity_score = min(len(genre_counter) / total_books, 1.0) if total_books > 0 else 0.0

    return {
        "chart_data": {
            "labels": [g for g, _ in top_8],
            "values": [c for _, c in top_8],
        },
        "diversity_score": round(diversity_score, 4),
        "top_genre": top_8[0][0],
        "genre_counts": dict(genre_counter.most_common()),
    }


# ---------------------------------------------------------------------------
# 5. Reading Pace
# ---------------------------------------------------------------------------

def compute_reading_pace(books):
    """Compute reading pace over time."""
    month_counts = Counter()
    year_counts = Counter()

    for b in books:
        dt = parse_date(b.get("date_read"))
        if dt is None:
            continue
        ym = dt.strftime("%Y-%m")
        month_counts[ym] += 1
        year_counts[dt.year] += 1

    if not month_counts:
        return {
            "books_per_year": 0.0,
            "books_per_month": 0.0,
            "chart_data": {"labels": [], "values": []},
            "peak_month": None,
            "peak_year": None,
            "total_years": 0,
        }

    sorted_months = sorted(month_counts.keys())
    sorted_values = [month_counts[m] for m in sorted_months]

    total_books_read = sum(month_counts.values())
    total_years = len(year_counts)
    total_months = len(month_counts)

    books_per_year = total_books_read / total_years if total_years > 0 else 0.0
    books_per_month = total_books_read / total_months if total_months > 0 else 0.0

    peak_month = max(month_counts, key=month_counts.get)
    peak_year = max(year_counts, key=year_counts.get)

    return {
        "books_per_year": round(books_per_year, 2),
        "books_per_month": round(books_per_month, 2),
        "chart_data": {"labels": sorted_months, "values": sorted_values},
        "peak_month": peak_month,
        "peak_year": peak_year,
        "total_years": total_years,
    }


# ---------------------------------------------------------------------------
# 6. Author Loyalty
# ---------------------------------------------------------------------------

def compute_author_loyalty(books):
    """Identify repeat authors and compute a loyalty score."""
    author_counter = Counter()

    for b in books:
        author = b.get("author")
        if author and isinstance(author, str) and author.strip():
            author_counter[author.strip()] += 1

    total_books = len(books)
    repeat_authors = {a: c for a, c in author_counter.items() if c >= 2}

    if not repeat_authors:
        return {
            "loyalty_score": 0.0,
            "top_authors": [],
            "chart_data": {"labels": [], "values": []},
            "repeat_author_count": 0,
        }

    books_by_repeat = sum(repeat_authors.values())
    loyalty_score = books_by_repeat / total_books if total_books > 0 else 0.0

    top_10 = sorted(repeat_authors.items(), key=lambda x: x[1], reverse=True)[:10]
    top_authors = [{"name": name, "count": count} for name, count in top_10]

    return {
        "loyalty_score": round(loyalty_score, 4),
        "top_authors": top_authors,
        "chart_data": {
            "labels": [a["name"] for a in top_authors],
            "values": [a["count"] for a in top_authors],
        },
        "repeat_author_count": len(repeat_authors),
    }


# ---------------------------------------------------------------------------
# 7. Rating Distribution
# ---------------------------------------------------------------------------

def compute_rating_distribution(books):
    """Histogram of user ratings 1-5."""
    ratings = []

    for b in books:
        r = safe_float(b.get("user_rating"))
        if r is not None and r > 0:
            ratings.append(r)

    counts = {str(i): 0 for i in range(1, 6)}
    for r in ratings:
        key = str(int(round(r)))
        if key in counts:
            counts[key] += 1

    labels = ["1", "2", "3", "4", "5"]
    values = [counts[l] for l in labels]

    if not ratings:
        return {
            "chart_data": {"labels": labels, "values": values},
            "average": 0.0,
            "median": 0.0,
            "total_rated": 0,
            "pct_5_star": 0.0,
        }

    avg = statistics.mean(ratings)
    med = statistics.median(ratings)
    total_rated = len(ratings)
    pct_5_star = (counts["5"] / total_rated) * 100 if total_rated > 0 else 0.0

    return {
        "chart_data": {"labels": labels, "values": values},
        "average": round(avg, 2),
        "median": round(med, 2),
        "total_rated": total_rated,
        "pct_5_star": round(pct_5_star, 2),
    }


# ---------------------------------------------------------------------------
# 8. Reading Heatmap
# ---------------------------------------------------------------------------

def compute_reading_heatmap(books):
    """GitHub-calendar-style reading heatmap for the last 365 days."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - timedelta(days=364)

    day_counts = Counter()

    for b in books:
        dt = parse_date(b.get("date_read"))
        if dt is None:
            continue
        dt_date = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        if start_date <= dt_date <= today:
            day_str = dt_date.strftime("%Y-%m-%d")
            day_counts[day_str] += 1

    # Build full daily_counts list (including zero-count days for completeness
    # is optional; we include only days that have reads, plus metadata).
    daily_counts = []
    current = start_date
    while current <= today:
        ds = current.strftime("%Y-%m-%d")
        if day_counts[ds] > 0:
            daily_counts.append({"date": ds, "count": day_counts[ds]})
        current += timedelta(days=1)

    # Max day
    if day_counts:
        max_day = max(day_counts, key=day_counts.get)
    else:
        max_day = None

    # Total days with at least one book read
    total_days_reading = len(day_counts)

    # Longest streak of consecutive reading days (within the 365-day window)
    streak_max = 0
    if day_counts:
        current_streak = 0
        current = start_date
        while current <= today:
            ds = current.strftime("%Y-%m-%d")
            if day_counts[ds] > 0:
                current_streak += 1
                if current_streak > streak_max:
                    streak_max = current_streak
            else:
                current_streak = 0
            current += timedelta(days=1)

    return {
        "daily_counts": daily_counts,
        "max_day": max_day,
        "total_days_reading": total_days_reading,
        "streak_max": streak_max,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON input: {exc}"}), file=sys.stderr)
        sys.exit(1)

    books = data.get("books", [])
    if not isinstance(books, list):
        books = []

    result = {
        "hater_hype": compute_hater_hype_index(books),
        "reading_eras": compute_reading_eras(books),
        "attention_span": compute_attention_span(books),
        "genre_radar": compute_genre_radar(books),
        "reading_pace": compute_reading_pace(books),
        "author_loyalty": compute_author_loyalty(books),
        "rating_distribution": compute_rating_distribution(books),
        "reading_heatmap": compute_reading_heatmap(books),
    }

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
