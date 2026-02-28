#!/usr/bin/env python3
"""Read combined JSON from stdin and upsert into Postgres."""

import argparse
import json
import os
import re
import sys

import psycopg2
import psycopg2.extensions
import psycopg2.extras

# Register the JSON adapter so Python dicts/lists are sent as JSONB.
psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)

UPSERT_PROFILE_SQL = """
INSERT INTO profiles (
    goodreads_id,
    username,
    profile_url,
    book_count,
    books_json,
    stats_json,
    ai_psychological,
    ai_roast,
    ai_vibe_check,
    ai_red_green_flags,
    ai_blind_spots,
    ai_reading_evolution,
    ai_recommendations,
    ai_deep_profile
) VALUES (
    %(goodreads_id)s,
    %(username)s,
    %(profile_url)s,
    %(book_count)s,
    %(books_json)s,
    %(stats_json)s,
    %(ai_psychological)s,
    %(ai_roast)s,
    %(ai_vibe_check)s,
    %(ai_red_green_flags)s,
    %(ai_blind_spots)s,
    %(ai_reading_evolution)s,
    %(ai_recommendations)s,
    %(ai_deep_profile)s
)
ON CONFLICT (goodreads_id) DO UPDATE SET
    username            = EXCLUDED.username,
    profile_url         = EXCLUDED.profile_url,
    book_count          = EXCLUDED.book_count,
    books_json          = EXCLUDED.books_json,
    stats_json          = EXCLUDED.stats_json,
    ai_psychological    = EXCLUDED.ai_psychological,
    ai_roast            = EXCLUDED.ai_roast,
    ai_vibe_check       = EXCLUDED.ai_vibe_check,
    ai_red_green_flags  = EXCLUDED.ai_red_green_flags,
    ai_blind_spots      = EXCLUDED.ai_blind_spots,
    ai_reading_evolution = EXCLUDED.ai_reading_evolution,
    ai_recommendations  = EXCLUDED.ai_recommendations,
    ai_deep_profile     = EXCLUDED.ai_deep_profile,
    updated_at          = NOW();
"""

UPSERT_COMPARISON_SQL = """
INSERT INTO comparisons (profile_a_id, profile_b_id, comparison_json)
VALUES (
    (SELECT id FROM profiles WHERE goodreads_id = %(profile_a_id)s),
    (SELECT id FROM profiles WHERE goodreads_id = %(profile_b_id)s),
    %(comparison_json)s
)
ON CONFLICT (profile_a_id, profile_b_id) DO UPDATE SET
    comparison_json = EXCLUDED.comparison_json,
    created_at      = NOW();
"""


def get_database_url() -> str:
    """Return DATABASE_URL from the environment."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return url


def store_profile(data: dict) -> None:
    """Upsert a profile row from the combined JSON payload."""
    database_url = get_database_url()

    user_id = data["user_id"]
    ai = data.get("ai_analyses") or {}

    params = {
        "goodreads_id":       user_id,
        "username":           data.get("user_name"),
        "profile_url":        f"https://www.goodreads.com/user/show/{user_id}",
        "book_count":         data["book_count"],
        "books_json":         data.get("books", []),
        "stats_json":         data.get("stats", {}),
        "ai_psychological":   ai.get("psychological"),
        "ai_roast":           ai.get("roast"),
        "ai_vibe_check":      ai.get("vibe_check"),
        "ai_red_green_flags": ai.get("red_green_flags"),
        "ai_blind_spots":     ai.get("blind_spots"),
        "ai_reading_evolution": ai.get("reading_evolution"),
        "ai_recommendations": ai.get("recommendations"),
        "ai_deep_profile":    ai.get("deep_profile"),
    }

    print(f"Upserting profile for Goodreads user {user_id}...", file=sys.stderr)

    try:
        conn = psycopg2.connect(database_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(UPSERT_PROFILE_SQL, params)
        conn.close()
    except psycopg2.Error as exc:
        print(f"ERROR: Failed to upsert profile: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Profile stored successfully.", file=sys.stderr)
    username = data.get("user_name") or user_id
    slug = re.sub(r'[^\w\s-]', '', username.lower().strip())
    slug = re.sub(r'[\s_]+', '-', slug).strip('-') or 'reader'
    print(f"shelf-aware.onrender.com/u/{slug}-{user_id}")


def store_comparison(data: dict) -> None:
    """Upsert a comparison row from the comparison JSON payload."""
    database_url = get_database_url()

    profile_a = data["profile_a_id"]
    profile_b = data["profile_b_id"]

    params = {
        "profile_a_id":   profile_a,
        "profile_b_id":   profile_b,
        "comparison_json": data["comparison"],
    }

    print(
        f"Upserting comparison for {profile_a} vs {profile_b}...",
        file=sys.stderr,
    )

    try:
        conn = psycopg2.connect(database_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(UPSERT_COMPARISON_SQL, params)
        conn.close()
    except psycopg2.Error as exc:
        print(f"ERROR: Failed to upsert comparison: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Comparison stored successfully.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read JSON from stdin and upsert into Postgres."
    )
    parser.add_argument(
        "--comparison",
        action="store_true",
        help="Treat input as a comparison payload instead of a profile.",
    )
    args = parser.parse_args()

    raw = sys.stdin.read()
    if not raw.strip():
        print("ERROR: No input received on stdin.", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON on stdin: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.comparison:
        store_comparison(data)
    else:
        store_profile(data)


if __name__ == "__main__":
    main()
