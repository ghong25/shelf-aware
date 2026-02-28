import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from server.database import get_profile

router = APIRouter()


@router.get("/u/{goodreads_id}", response_class=HTMLResponse)
async def profile_page(request: Request, goodreads_id: str):
    profile = await get_profile(goodreads_id)
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
    ]:
        val = profile.get(key)
        if val is not None:
            ai_sections[key.removeprefix("ai_")] = val if isinstance(val, dict) else json.loads(val)

    return request.app.state.templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "profile": profile,
            "stats": stats,
            "books": books,
            "ai": ai_sections,
            "stats_json": json.dumps(stats),
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
                ]
                if profile.get(k)
            },
        }
    )
