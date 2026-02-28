import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from server.database import get_comparison, get_profile

router = APIRouter()


@router.get("/compare/{id1}-vs-{id2}", response_class=HTMLResponse)
async def compare_page(request: Request, id1: str, id2: str):
    comparison = await get_comparison(id1, id2)
    profile_a = await get_profile(id1)
    profile_b = await get_profile(id2)

    if comparison is None or profile_a is None or profile_b is None:
        return request.app.state.templates.TemplateResponse(
            "home.html",
            {"request": request, "error": "Comparison not found", "recent": []},
            status_code=404,
        )

    stats_a = profile_a["stats_json"] if isinstance(profile_a["stats_json"], dict) else json.loads(profile_a["stats_json"])
    stats_b = profile_b["stats_json"] if isinstance(profile_b["stats_json"], dict) else json.loads(profile_b["stats_json"])
    comp_data = comparison["comparison_json"] if isinstance(comparison["comparison_json"], dict) else json.loads(comparison["comparison_json"])

    hard_stats = comp_data.get("hard_stats", {})
    dynamics = comp_data.get("dynamics", {})
    recs = comp_data.get("recommendations", {})

    return request.app.state.templates.TemplateResponse(
        "compare.html",
        {
            "request": request,
            "profile_a": profile_a,
            "profile_b": profile_b,
            "stats_a": stats_a,
            "stats_b": stats_b,
            "hard_stats": hard_stats,
            "dynamics": dynamics,
            "recs": recs,
            "comp_json": json.dumps(hard_stats),
        },
    )
