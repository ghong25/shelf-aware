#!/usr/bin/env python3
"""Create Postgres tables for Shelf Aware."""

import os
import sys

import psycopg2
import psycopg2.extensions
import psycopg2.extras

# Register the JSON adapter so Python dicts are sent as JSONB.
psycopg2.extensions.register_adapter(dict, psycopg2.extras.Json)
psycopg2.extensions.register_adapter(list, psycopg2.extras.Json)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS profiles (
    id                  SERIAL PRIMARY KEY,
    goodreads_id        VARCHAR(32) UNIQUE NOT NULL,
    username            VARCHAR(255),
    profile_url         VARCHAR(512),
    book_count          INTEGER NOT NULL,
    books_json          JSONB NOT NULL,
    stats_json          JSONB NOT NULL,
    ai_psychological    JSONB,
    ai_roast            JSONB,
    ai_vibe_check       JSONB,
    ai_red_green_flags  JSONB,
    ai_blind_spots      JSONB,
    ai_reading_evolution JSONB,
    ai_recommendations  JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS comparisons (
    id              SERIAL PRIMARY KEY,
    profile_a_id    INTEGER REFERENCES profiles(id),
    profile_b_id    INTEGER REFERENCES profiles(id),
    comparison_json JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(profile_a_id, profile_b_id)
);
"""


def get_database_url() -> str:
    """Return DATABASE_URL from the environment or a .env file."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    # Fall back to .env file in the project root.
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key == "DATABASE_URL":
                    return value

    print("ERROR: DATABASE_URL not set and no .env file found.", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    database_url = get_database_url()

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.close()
        print("Tables created successfully.", file=sys.stderr)
    except psycopg2.Error as exc:
        print(f"ERROR: Failed to create tables: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
