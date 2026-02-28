import asyncpg
import json
import os


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
