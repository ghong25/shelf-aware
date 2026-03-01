import asyncio
import asyncpg
import hashlib
import json
import os
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

    vitals, comp_count, archetype_row = await asyncio.gather(
        pool.fetchrow("""
            SELECT
                COUNT(*)                                                                AS total_profiles,
                COALESCE(SUM(book_count), 0)                                           AS total_books,
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
        pool.fetchrow("""
            SELECT ai_psychological->>'archetype' AS archetype, COUNT(*) AS cnt
            FROM profiles
            WHERE ai_psychological IS NOT NULL
              AND ai_psychological->>'archetype' IS NOT NULL
            GROUP BY archetype
            ORDER BY cnt DESC
            LIMIT 1
        """),
    )

    total_with_stats = (vitals["hype_count"] or 0) + (vitals["critic_count"] or 0)
    hype_pct = round((vitals["hype_count"] or 0) * 100 / total_with_stats) if total_with_stats else None

    result = {
        "total_profiles":    int(vitals["total_profiles"]),
        "total_books":       int(vitals["total_books"]),
        "total_comparisons": int(comp_count or 0),
        "avg_rating_delta":  round(float(vitals["avg_rating_delta"]), 2) if vitals["avg_rating_delta"] is not None else None,
        "hype_pct":          hype_pct,
        "critic_pct":        (100 - hype_pct) if hype_pct is not None else None,
        "dominant_archetype": archetype_row["archetype"] if archetype_row else None,
    }

    _platform_stats_cache = result
    _platform_stats_cache_time = time.time()
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
                        url1: str, url2: str | None = None) -> None:
    await get_pool().execute(
        """INSERT INTO analysis_requests
           (request_type, requester_name, goodreads_url_1, goodreads_url_2)
           VALUES ($1, $2, $3, $4)""",
        request_type, requester_name, url1, url2,
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
