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
        """SELECT goodreads_id, username, book_count, created_at, updated_at
           FROM profiles ORDER BY updated_at DESC LIMIT $1""",
        limit,
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
