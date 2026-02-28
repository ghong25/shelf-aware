import asyncio
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from server.database import get_benchmark_stats, get_profile, log_page_view


def slugify(text: str) -> str:
    """Convert username to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text.strip('-') or 'reader'


router = APIRouter()


@router.get("/u/{slug}-{goodreads_id}", response_class=HTMLResponse)
async def profile_page_with_slug(request: Request, slug: str, goodreads_id: str):
    """Profile page with human-readable slug in URL."""
    return await _render_profile(request, goodreads_id)


@router.get("/u/{goodreads_id}", response_class=HTMLResponse)
async def profile_page(request: Request, goodreads_id: str):
    """Bare ID URL — redirect to slugged version if profile exists."""
    profile = await get_profile(goodreads_id)
    if profile is None:
        return request.app.state.templates.TemplateResponse(
            "home.html",
            {"request": request, "error": "Profile not found", "recent": []},
            status_code=404,
        )
    slug = slugify(profile.get("username") or goodreads_id)
    return RedirectResponse(url=f"/u/{slug}-{goodreads_id}", status_code=301)


def _get_client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def _render_profile(request: Request, goodreads_id: str):
    profile, benchmarks = await asyncio.gather(
        get_profile(goodreads_id),
        get_benchmark_stats(goodreads_id),
    )
    if profile is None:
        return request.app.state.templates.TemplateResponse(
            "home.html",
            {"request": request, "error": "Profile not found", "recent": []},
            status_code=404,
        )

    stats = profile["stats_json"] if isinstance(profile["stats_json"], dict) else json.loads(profile["stats_json"])
    books = profile["books_json"] if isinstance(profile["books_json"], list) else json.loads(profile["books_json"])

    ai_sections = {}
    for key in [
        "ai_psychological",
        "ai_roast",
        "ai_vibe_check",
        "ai_red_green_flags",
        "ai_blind_spots",
        "ai_reading_evolution",
        "ai_recommendations",
        "ai_deep_profile",
    ]:
        val = profile.get(key)
        if val is not None:
            ai_sections[key.removeprefix("ai_")] = val if isinstance(val, dict) else json.loads(val)

    asyncio.create_task(log_page_view(
        "profile", goodreads_id,
        _get_client_ip(request),
        request.headers.get("Referer"),
    ))

    return request.app.state.templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "profile": profile,
            "stats": stats,
            "books": books,
            "ai": ai_sections,
            "stats_json": json.dumps(stats),
            "benchmarks": benchmarks,
            "benchmarks_json": json.dumps(benchmarks or {}),
        },
    )


@router.get("/api/profile/{goodreads_id}", response_class=JSONResponse)
async def profile_api(goodreads_id: str):
    profile = await get_profile(goodreads_id)
    if profile is None:
        return JSONResponse({"error": "not found"}, status_code=404)

    return JSONResponse(
        {
            "goodreads_id": profile["goodreads_id"],
            "username": profile["username"],
            "book_count": profile["book_count"],
            "stats": profile["stats_json"],
            "ai": {
                k.removeprefix("ai_"): profile[k]
                for k in [
                    "ai_psychological",
                    "ai_roast",
                    "ai_vibe_check",
                    "ai_red_green_flags",
                    "ai_blind_spots",
                    "ai_reading_evolution",
                    "ai_recommendations",
                    "ai_deep_profile",
                ]
                if profile.get(k)
            },
        }
    )
