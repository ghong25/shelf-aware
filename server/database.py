import asyncio
import asyncpg
import hashlib
import json
import os
import random
import re
import time


_pool: asyncpg.Pool | None = None


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
        command_timeout=30,
    )


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    assert _pool is not None, "Database pool not initialized"
    return _pool


async def get_profile(goodreads_id: str) -> dict | None:
    row = await get_pool().fetchrow(
        "SELECT * FROM profiles WHERE goodreads_id = $1", goodreads_id
    )
    if row is None:
        return None
    return dict(row)


async def get_recent_profiles(limit: int = 12) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT goodreads_id, username, book_count, created_at, updated_at,
                  ai_psychological->>'archetype' AS archetype,
                  stats_json->'genre_radar'->>'top_genre' AS top_genre
           FROM profiles ORDER BY updated_at DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


async def get_recent_comparisons(limit: int = 6) -> list[dict]:
    rows = await get_pool().fetch(
        """SELECT
               pa.goodreads_id AS id_a, pa.username AS username_a,
               pb.goodreads_id AS id_b, pb.username AS username_b,
               c.comparison_json->'dynamics'->>'compatibility_score' AS compatibility_score,
               c.comparison_json->'dynamics'->>'dynamic_trope' AS dynamic_trope,
               c.created_at
           FROM comparisons c
           JOIN profiles pa ON c.profile_a_id = pa.id
           JOIN profiles pb ON c.profile_b_id = pb.id
           ORDER BY c.created_at DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


_platform_stats_cache: dict | None = None
_platform_stats_cache_time: float = 0.0
_PLATFORM_STATS_TTL = 600  # 10 minutes


async def get_platform_stats() -> dict:
    global _platform_stats_cache, _platform_stats_cache_time
    if _platform_stats_cache and (time.time() - _platform_stats_cache_time) < _PLATFORM_STATS_TTL:
        return _platform_stats_cache

    pool = get_pool()

    vitals, comp_count, archetype_rows, top_genres_rows, patron_row, overrated_row = await asyncio.gather(
        pool.fetchrow("""
            SELECT
                COUNT(*)                                                                AS total_profiles,
                COALESCE(SUM(book_count), 0)                                           AS total_books,
                AVG(book_count)::int                                                    AS avg_books_per_reader,
                AVG(CASE
                    WHEN stats_json->'hater_hype' IS NOT NULL
                    THEN (stats_json->'hater_hype'->>'mean_diff')::float
                END)                                                                    AS avg_rating_delta,
                COUNT(*) FILTER (
                    WHERE stats_json->'hater_hype' IS NOT NULL
                    AND (stats_json->'hater_hype'->>'mean_diff')::float >= 0
                )                                                                       AS hype_count,
                COUNT(*) FILTER (
                    WHERE stats_json->'hater_hype' IS NOT NULL
                    AND (stats_json->'hater_hype'->>'mean_diff')::float < 0
                )                                                                       AS critic_count
            FROM profiles
        """),
        pool.fetchval("SELECT COUNT(*) FROM comparisons"),
        pool.fetch("""
            SELECT ai_psychological->>'archetype' AS archetype, COUNT(*) AS cnt
            FROM profiles
            WHERE ai_psychological IS NOT NULL
              AND ai_psychological->>'archetype' IS NOT NULL
            GROUP BY archetype
            ORDER BY cnt DESC
            LIMIT 5
        """),
        pool.fetch("""
            SELECT genre, SUM(cnt::int) AS total
            FROM profiles,
                 LATERAL jsonb_each_text(stats_json->'genre_radar'->'genre_counts') AS g(genre, cnt)
            WHERE stats_json->'genre_radar'->'genre_counts' IS NOT NULL
            GROUP BY genre
            ORDER BY total DESC
            LIMIT 6
        """),
        pool.fetchrow("""
            SELECT
                b->>'author' AS author,
                COUNT(*) AS book_count,
                array_agg(DISTINCT b->>'cover_url') FILTER (
                    WHERE b->>'cover_url' IS NOT NULL AND b->>'cover_url' != ''
                ) AS covers
            FROM profiles,
                 LATERAL jsonb_array_elements(books_json) AS b
            WHERE books_json IS NOT NULL
            GROUP BY b->>'author'
            ORDER BY book_count DESC
            LIMIT 1
        """),
        pool.fetchrow("""
            SELECT
                b->>'title'          AS title,
                b->>'author'         AS author,
                b->>'cover_url'      AS cover_url,
                (b->>'user_rating')::float   AS user_rating,
                (b->>'average_rating')::float AS goodreads_avg,
                (b->>'user_rating')::float - (b->>'average_rating')::float AS delta
            FROM profiles,
                 LATERAL jsonb_array_elements(books_json) AS b
            WHERE books_json IS NOT NULL
              AND (b->>'user_rating') IS NOT NULL
              AND (b->>'user_rating')::float > 0
              AND (b->>'average_rating') IS NOT NULL
              AND (b->>'average_rating')::float > 0
            ORDER BY delta ASC
            LIMIT 1
        """),
    )

    total_with_stats = (vitals["hype_count"] or 0) + (vitals["critic_count"] or 0)
    hype_pct = round((vitals["hype_count"] or 0) * 100 / total_with_stats) if total_with_stats else None

    # Archetype breakdown with percentages
    total_archetypes = sum(r["cnt"] for r in archetype_rows)
    archetype_breakdown = [
        {
            "archetype": r["archetype"],
            "count": int(r["cnt"]),
            "pct": round(int(r["cnt"]) * 100 / total_archetypes) if total_archetypes else 0,
        }
        for r in archetype_rows
    ]

    # Top genres list
    top_genres = [{"genre": r["genre"], "count": int(r["total"])} for r in top_genres_rows]

    # Patron saint author
    patron_saint = None
    if patron_row and patron_row["author"]:
        covers = patron_row["covers"] or []
        patron_saint = {
            "author": patron_row["author"],
            "book_count": int(patron_row["book_count"]),
            "covers": covers[:3],
        }

    # Overrated book
    overrated_book = None
    if overrated_row and overrated_row["cover_url"]:
        overrated_book = {
            "title": overrated_row["title"],
            "author": overrated_row["author"],
            "cover_url": overrated_row["cover_url"],
            "user_rating": float(overrated_row["user_rating"]),
            "goodreads_avg": float(overrated_row["goodreads_avg"]),
            "delta": round(float(overrated_row["delta"]), 2),
        }

    result = {
        "total_profiles":      int(vitals["total_profiles"]),
        "total_books":         int(vitals["total_books"]),
        "avg_books_per_reader": int(vitals["avg_books_per_reader"]) if vitals["avg_books_per_reader"] is not None else None,
        "total_comparisons":   int(comp_count or 0),
        "avg_rating_delta":    round(float(vitals["avg_rating_delta"]), 2) if vitals["avg_rating_delta"] is not None else None,
        "hype_pct":            hype_pct,
        "critic_pct":          (100 - hype_pct) if hype_pct is not None else None,
        "dominant_archetype":  archetype_rows[0]["archetype"] if archetype_rows else None,
        "archetype_breakdown": archetype_breakdown,
        "top_genres":          top_genres,
        "patron_saint":        patron_saint,
        "overrated_book":      overrated_book,
    }

    _platform_stats_cache = result
    _platform_stats_cache_time = time.time()
    return result


_roast_snippets_cache: list | None = None
_roast_snippets_cache_time: float = 0.0


async def get_roast_snippets() -> list[str]:
    global _roast_snippets_cache, _roast_snippets_cache_time
    if _roast_snippets_cache is not None and (time.time() - _roast_snippets_cache_time) < _PLATFORM_STATS_TTL:
        return _roast_snippets_cache

    rows = await get_pool().fetch("""
        SELECT ai_roast->>'one_liner' AS one_liner
        FROM profiles
        WHERE ai_roast IS NOT NULL AND ai_roast->>'one_liner' IS NOT NULL
    """)
    result = [r["one_liner"] for r in rows if r["one_liner"]]
    _roast_snippets_cache = result
    _roast_snippets_cache_time = time.time()
    return result


_era_distribution_cache: dict | None = None
_era_distribution_cache_time: float = 0.0


async def get_era_distribution() -> dict:
    global _era_distribution_cache, _era_distribution_cache_time
    if _era_distribution_cache is not None and (time.time() - _era_distribution_cache_time) < _PLATFORM_STATS_TTL:
        return _era_distribution_cache

    rows = await get_pool().fetch("""
        SELECT stats_json->'reading_eras'->'chart_data' AS era_data
        FROM profiles
        WHERE stats_json->'reading_eras' IS NOT NULL
          AND stats_json->'reading_eras'->'chart_data' IS NOT NULL
    """)

    decade_totals: dict[str, int] = {}
    for row in rows:
        era_data = row["era_data"]
        if not era_data:
            continue
        try:
            if isinstance(era_data, str):
                era_data = json.loads(era_data)
            labels = era_data.get("labels", [])
            values = era_data.get("values", [])
            for label, value in zip(labels, values):
                decade_totals[label] = decade_totals.get(label, 0) + int(value or 0)
        except (KeyError, TypeError, ValueError):
            continue

    bucketed: dict[str, int] = {}
    for label, count in decade_totals.items():
        m = re.match(r'(\d+)', label)
        if not m:
            continue
        year = int(m.group(1))
        if year < 1800:
            key = 'Pre-1800'
        elif year < 1900:
            key = '1800s'
        else:
            key = label
        bucketed[key] = bucketed.get(key, 0) + count

    def sort_key(k: str) -> int:
        if k == 'Pre-1800': return 0
        if k == '1800s': return 1
        m = re.match(r'(\d+)', k)
        return int(m.group(1)) if m else 9999

    sorted_items = sorted(bucketed.items(), key=lambda x: sort_key(x[0]))
    result = {
        "labels": [d[0] for d in sorted_items],
        "values": [d[1] for d in sorted_items],
    }
    _era_distribution_cache = result
    _era_distribution_cache_time = time.time()
    return result


_book_covers_cache: list | None = None
_book_covers_cache_time: float = 0.0


async def get_platform_book_covers(limit: int = 100) -> list[dict]:
    global _book_covers_cache, _book_covers_cache_time
    if _book_covers_cache is not None and (time.time() - _book_covers_cache_time) < _PLATFORM_STATS_TTL:
        return _book_covers_cache

    rows = await get_pool().fetch("""
        SELECT DISTINCT ON (book->>'cover_url') book->>'cover_url' AS cover_url, book->>'title' AS title
        FROM profiles, LATERAL jsonb_array_elements(books_json) AS book
        WHERE book->>'cover_url' IS NOT NULL AND book->>'cover_url' != ''
        ORDER BY book->>'cover_url'
        LIMIT $1
    """, limit)
    result = [{"cover_url": r["cover_url"], "title": r["title"]} for r in rows]
    random.shuffle(result)
    _book_covers_cache = result
    _book_covers_cache_time = time.time()
    return result


async def get_benchmark_stats(goodreads_id: str) -> dict | None:
    row = await get_pool().fetchrow(
        """
        WITH user_stat AS (
            SELECT
                (stats_json->'attention_span'->>'avg_pages')::float       AS avg_pages,
                (stats_json->'reading_pace'->>'books_per_year')::float    AS books_per_year,
                (stats_json->'genre_radar'->>'diversity_score')::float    AS diversity_score,
                (stats_json->'rating_distribution'->>'average')::float   AS avg_rating
            FROM profiles WHERE goodreads_id = $1
        ),
        pop AS (
            SELECT
                (stats_json->'attention_span'->>'avg_pages')::float       AS avg_pages,
                (stats_json->'reading_pace'->>'books_per_year')::float    AS books_per_year,
                (stats_json->'genre_radar'->>'diversity_score')::float    AS diversity_score,
                (stats_json->'rating_distribution'->>'average')::float   AS avg_rating
            FROM profiles
            WHERE (stats_json->'attention_span'->>'avg_pages') IS NOT NULL
              AND (stats_json->'attention_span'->>'avg_pages')::float > 0
        )
        SELECT
            ROUND((SELECT COUNT(*) FROM pop WHERE avg_pages       < (SELECT avg_pages       FROM user_stat)) * 100.0 / NULLIF(COUNT(*),0)) AS pages_pct,
            ROUND((SELECT COUNT(*) FROM pop WHERE books_per_year  < (SELECT books_per_year  FROM user_stat)) * 100.0 / NULLIF(COUNT(*),0)) AS pace_pct,
            ROUND((SELECT COUNT(*) FROM pop WHERE diversity_score < (SELECT diversity_score FROM user_stat)) * 100.0 / NULLIF(COUNT(*),0)) AS diversity_pct,
            ROUND((SELECT COUNT(*) FROM pop WHERE avg_rating      < (SELECT avg_rating      FROM user_stat)) * 100.0 / NULLIF(COUNT(*),0)) AS rating_pct,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY avg_pages)      AS median_pages,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY books_per_year) AS median_bpy,
            COUNT(*) AS total_profiles
        FROM pop
        """,
        goodreads_id,
    )
    if row is None:
        return None
    d = dict(row)
    if d.get("total_profiles") is None or d["total_profiles"] < 5:
        return None
    return {
        "pages_pct": int(d["pages_pct"]) if d["pages_pct"] is not None else None,
        "pace_pct": int(d["pace_pct"]) if d["pace_pct"] is not None else None,
        "diversity_pct": int(d["diversity_pct"]) if d["diversity_pct"] is not None else None,
        "rating_pct": int(d["rating_pct"]) if d["rating_pct"] is not None else None,
        "median_pages": round(float(d["median_pages"]), 1) if d["median_pages"] is not None else None,
        "median_bpy": round(float(d["median_bpy"]), 1) if d["median_bpy"] is not None else None,
        "total_profiles": int(d["total_profiles"]),
    }


async def log_page_view(page_type: str, entity_id: str | None, ip: str | None, referrer: str | None) -> None:
    try:
        ip_hash = hashlib.sha256((ip or "").encode()).hexdigest()[:16] if ip else None
        await get_pool().execute(
            "INSERT INTO page_views (page_type, entity_id, ip_hash, referrer) VALUES ($1, $2, $3, $4)",
            page_type, entity_id, ip_hash, referrer,
        )
    except Exception:
        pass


async def get_analytics() -> dict:
    pool = get_pool()

    totals, by_type, top_profiles, top_comparisons, daily = await asyncio.gather(
        pool.fetchrow("""
            SELECT
                COUNT(*)                                                              AS total_views,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')       AS views_7d,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days')      AS views_30d,
                COUNT(DISTINCT ip_hash)                                               AS unique_visitors
            FROM page_views
        """),
        pool.fetch("""
            SELECT
                page_type,
                COUNT(*)                                                              AS total,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')       AS last_7d,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days')      AS last_30d,
                COUNT(DISTINCT ip_hash)                                               AS unique_visitors
            FROM page_views
            GROUP BY page_type ORDER BY total DESC
        """),
        pool.fetch("""
            SELECT
                pv.entity_id,
                p.username,
                COUNT(*)                    AS views,
                COUNT(DISTINCT pv.ip_hash)  AS unique_views,
                MAX(pv.created_at)          AS last_viewed
            FROM page_views pv
            LEFT JOIN profiles p ON p.goodreads_id = pv.entity_id
            WHERE pv.page_type = 'profile'
            GROUP BY pv.entity_id, p.username
            ORDER BY views DESC LIMIT 15
        """),
        pool.fetch("""
            SELECT
                pv.entity_id,
                pa.username AS username_a,
                pb.username AS username_b,
                COUNT(*)           AS views,
                MAX(pv.created_at) AS last_viewed
            FROM page_views pv
            LEFT JOIN profiles pa ON pa.goodreads_id = SPLIT_PART(pv.entity_id, '-vs-', 1)
            LEFT JOIN profiles pb ON pb.goodreads_id = SPLIT_PART(pv.entity_id, '-vs-', 2)
            WHERE pv.page_type = 'compare'
            GROUP BY pv.entity_id, pa.username, pb.username
            ORDER BY views DESC LIMIT 10
        """),
        pool.fetch("""
            SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS views
            FROM page_views
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY day ORDER BY day
        """),
    )

    return {
        "totals": dict(totals) if totals else {},
        "by_type": [dict(r) for r in by_type],
        "top_profiles": [dict(r) for r in top_profiles],
        "top_comparisons": [dict(r) for r in top_comparisons],
        "daily": [{"day": str(r["day"]), "views": r["views"]} for r in daily],
    }


def extract_goodreads_id(url: str) -> str | None:
    """Extract numeric Goodreads user ID from a profile URL."""
    m = re.search(r'/user/show/(\d+)', url)
    return m.group(1) if m else None


async def ensure_requests_table():
    await get_pool().execute("""
        CREATE TABLE IF NOT EXISTS analysis_requests (
            id SERIAL PRIMARY KEY,
            request_type VARCHAR(20) NOT NULL,
            requester_name VARCHAR(255),
            goodreads_url_1 VARCHAR(500) NOT NULL,
            goodreads_url_2 VARCHAR(500),
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)


async def store_request(request_type: str, requester_name: str,
                        url1: str, url2: str | None = None,
                        status: str = "pending") -> None:
    await get_pool().execute(
        """INSERT INTO analysis_requests
           (request_type, requester_name, goodreads_url_1, goodreads_url_2, status)
           VALUES ($1, $2, $3, $4, $5)""",
        request_type, requester_name, url1, url2, status,
    )


async def fulfill_profile_requests(goodreads_id: str) -> None:
    """Mark any pending profile requests for this user as fulfilled."""
    await get_pool().execute(
        """UPDATE analysis_requests
           SET status = 'fulfilled'
           WHERE status = 'pending'
             AND request_type = 'profile'
             AND goodreads_url_1 LIKE $1""",
        f"%/user/show/{goodreads_id}%",
    )


async def fulfill_comparison_requests(id_a: str, id_b: str) -> None:
    """Mark any pending comparison requests for this pair as fulfilled."""
    await get_pool().execute(
        """UPDATE analysis_requests
           SET status = 'fulfilled'
           WHERE status = 'pending'
             AND request_type = 'comparison'
             AND (
               (goodreads_url_1 LIKE $1 AND goodreads_url_2 LIKE $2)
               OR (goodreads_url_1 LIKE $2 AND goodreads_url_2 LIKE $1)
             )""",
        f"%/user/show/{id_a}%",
        f"%/user/show/{id_b}%",
    )


async def get_pending_requests() -> list[dict]:
    rows = await get_pool().fetch(
        "SELECT * FROM analysis_requests WHERE status = 'pending' ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


async def get_comparison(id1: str, id2: str) -> dict | None:
    row = await get_pool().fetchrow(
        """SELECT c.*, pa.goodreads_id AS gid_a, pb.goodreads_id AS gid_b
           FROM comparisons c
           JOIN profiles pa ON c.profile_a_id = pa.id
           JOIN profiles pb ON c.profile_b_id = pb.id
           WHERE (pa.goodreads_id = $1 AND pb.goodreads_id = $2)
              OR (pa.goodreads_id = $2 AND pb.goodreads_id = $1)""",
        id1,
        id2,
    )
    if row is None:
        return None
    return dict(row)
