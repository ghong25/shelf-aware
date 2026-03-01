#!/usr/bin/env python3
"""Migrate old rating style labels in stats_json to their new names."""

import os
import sys

import psycopg2

RENAMES = {
    "Hype Machine": "Rose-Tinted",
    "Straight Shooter": "The Consensus",
    "Plays It Safe": "The Conformist",
}

MIGRATE_SQL = """
UPDATE profiles
SET stats_json = jsonb_set(
    stats_json,
    '{hater_hype,label}',
    to_jsonb(%(new_label)s::text)
)
WHERE stats_json->'hater_hype'->>'label' = %(old_label)s;
"""


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

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
        with conn:
            with conn.cursor() as cur:
                for old_label, new_label in RENAMES.items():
                    cur.execute(MIGRATE_SQL, {"old_label": old_label, "new_label": new_label})
                    print(f"  {old_label!r} → {new_label!r}: {cur.rowcount} row(s) updated")
        conn.close()
        print("Migration complete.")
    except psycopg2.Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
