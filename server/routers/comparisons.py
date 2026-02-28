import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from server.database import get_comparison, get_profile
from server.routers.profiles import slugify

router = APIRouter()


@router.get("/compare/{comparison_slug}", response_class=HTMLResponse)
async def compare_page(request: Request, comparison_slug: str):
    # Try new slugged format: name-id1-vs-name-id2
    m = re.match(r'^(.*)-(\d+)-vs-(.*)-(\d+)$', comparison_slug)
    if m:
        _, id1, _, id2 = m.groups()
    else:
        # Try legacy format: id1-vs-id2 and redirect to slugged URL
        m_old = re.match(r'^(\d+)-vs-(\d+)$', comparison_slug)
        if m_old:
            id1, id2 = m_old.groups()
            profile_a = await get_profile(id1)
            profile_b = await get_profile(id2)
            if profile_a and profile_b:
                slug_a = slugify(profile_a.get("username") or id1)
                slug_b = slugify(profile_b.get("username") or id2)
                return RedirectResponse(
                    url=f"/compare/{slug_a}-{id1}-vs-{slug_b}-{id2}",
                    status_code=301,
                )
        return request.app.state.templates.TemplateResponse(
            "home.html",
            {"request": request, "error": "Comparison not found", "recent": []},
            status_code=404,
        )

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

    # Strip any leading "XX% — " or "XX% - " the AI baked into the line
    if dynamics.get("compatibility_line"):
        dynamics["compatibility_line"] = re.sub(r"^\d+%\s*[—-]\s*", "", dynamics["compatibility_line"])

    _ai_keys = ["ai_psychological", "ai_vibe_check", "ai_red_green_flags"]

    def _parse_ai(profile):
        result = {}
        for key in _ai_keys:
            val = profile.get(key)
            if val is not None:
                result[key.removeprefix("ai_")] = val if isinstance(val, dict) else json.loads(val)
        return result

    ai_a = _parse_ai(profile_a)
    ai_b = _parse_ai(profile_b)

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
            "ai_a": ai_a,
            "ai_b": ai_b,
        },
    )
