#!/usr/bin/env python3
"""
Backfill archetype_tagline for existing profiles that don't have it yet.

Reads each profile's ai_psychological JSON, calls Claude to generate a
1-sentence tagline from the existing archetype + summary, and writes it back.

Usage:
    DATABASE_URL="..." uv run python cli/backfill_archetype_taglines.py
    DATABASE_URL="..." uv run python cli/backfill_archetype_taglines.py --dry-run
"""

import argparse
import json
import os
import sys

import anthropic
import psycopg2
import psycopg2.extras

FETCH_SQL = """
SELECT goodreads_id, username, ai_psychological
FROM profiles
WHERE ai_psychological IS NOT NULL
  AND ai_psychological->>'archetype_tagline' IS NULL
ORDER BY updated_at DESC;
"""

UPDATE_SQL = """
UPDATE profiles
SET ai_psychological = ai_psychological || jsonb_build_object('archetype_tagline', %(tagline)s::text)
WHERE goodreads_id = %(goodreads_id)s;
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
                if key.strip() == "DATABASE_URL":
                    return value.strip().strip("\"'")
    print("ERROR: DATABASE_URL not set.", file=sys.stderr)
    sys.exit(1)


def generate_tagline(client: anthropic.Anthropic, archetype: str, summary: str) -> str:
    prompt = (
        f"A reader's archetype is \"{archetype}\".\n\n"
        f"Their psychological summary is: {summary}\n\n"
        "Write a single sentence (maximum 20 words) that defines what fundamentally drives "
        "this reader — their core motivation as a reader. "
        "Do not start with 'They' or repeat the archetype name. "
        "Return only the sentence, no quotes, no extra text."
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=60,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip().strip('"')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print taglines without writing to DB")
    args = parser.parse_args()

    database_url = get_database_url()
    client = anthropic.Anthropic()

    conn = psycopg2.connect(database_url)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(FETCH_SQL)
        rows = cur.fetchall()

    print(f"Found {len(rows)} profile(s) missing archetype_tagline.")
    if not rows:
        print("Nothing to do.")
        return

    updates = []
    for row in rows:
        psych = row["ai_psychological"]
        if isinstance(psych, str):
            psych = json.loads(psych)

        archetype = psych.get("archetype", "")
        summary = psych.get("summary", "")
        if not archetype or not summary:
            print(f"  Skipping {row['username'] or row['goodreads_id']} — missing archetype or summary")
            continue

        tagline = generate_tagline(client, archetype, summary)
        print(f"  {row['username'] or row['goodreads_id']} ({archetype}): {tagline}")
        updates.append({"goodreads_id": row["goodreads_id"], "tagline": tagline})

    if args.dry_run:
        print("\nDry run — no changes written.")
        return

    with conn:
        with conn.cursor() as cur:
            for u in updates:
                cur.execute(UPDATE_SQL, u)
    conn.close()
    print(f"\nUpdated {len(updates)} profile(s).")


if __name__ == "__main__":
    main()
