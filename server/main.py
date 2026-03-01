import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.database import (close_pool, ensure_requests_table, get_analytics,
                              get_comparison, get_era_distribution,
                              get_pending_requests, get_platform_book_covers,
                              get_platform_stats, get_profile,
                              get_recent_comparisons, get_recent_profiles,
                              get_roast_snippets, extract_goodreads_id,
                              init_pool, log_page_view, store_request)
from server.routers import comparisons, profiles
from server.routers.profiles import _get_client_ip, slugify

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await ensure_requests_table()
    yield
    await close_pool()


app = FastAPI(title="Shelf Aware", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["slugify"] = slugify
templates.env.filters["format_number"] = lambda n: "{:,}".format(int(n)) if n else "0"
app.state.templates = templates

app.include_router(profiles.router)
app.include_router(comparisons.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    recent, recent_comparisons, platform_stats, roast_snippets, era_dist, book_covers = await asyncio.gather(
        get_recent_profiles(limit=12),
        get_recent_comparisons(limit=6),
        get_platform_stats(),
        get_roast_snippets(),
        get_era_distribution(),
        get_platform_book_covers(limit=100),
    )
    asyncio.create_task(log_page_view(
        "home", None,
        _get_client_ip(request),
        request.headers.get("Referer"),
    ))
    return templates.TemplateResponse(
        "home.html", {
            "request": request,
            "recent": recent,
            "recent_comparisons": recent_comparisons,
            "platform_stats": platform_stats,
            "roast_snippets": roast_snippets,
            "era_dist": era_dist,
            "book_covers": book_covers,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            "exists_profile": request.query_params.get("exists_profile"),
            "exists_comparison": request.query_params.get("exists_comparison"),
        }
    )


@app.post("/request/profile")
async def request_profile(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    url = (form.get("goodreads_url") or "").strip()
    if not url:
        return RedirectResponse("/?error=Please+provide+a+Goodreads+URL", 303)

    gid = extract_goodreads_id(url)
    existing = await get_profile(gid) if gid else None
    if existing:
        profile_slug = slugify(existing.get("username") or gid)
        profile_path = f"/u/{profile_slug}-{existing['goodreads_id']}"
        await store_request("profile", name, url, status="fulfilled")
        from urllib.parse import quote
        return RedirectResponse(f"/?exists_profile={quote(profile_path, safe='/')}", 303)

    await store_request("profile", name, url)
    return RedirectResponse("/?success=profile", 303)


@app.post("/request/comparison")
async def request_comparison(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    url1 = (form.get("goodreads_url_1") or "").strip()
    url2 = (form.get("goodreads_url_2") or "").strip()
    if not url1 or not url2:
        return RedirectResponse("/?error=Please+provide+both+Goodreads+URLs", 303)

    id1 = extract_goodreads_id(url1)
    id2 = extract_goodreads_id(url2)
    existing = await get_comparison(id1, id2) if id1 and id2 else None
    if existing:
        profile_a = await get_profile(id1)
        profile_b = await get_profile(id2)
        slug_a = slugify(profile_a.get("username") or id1) if profile_a else id1
        slug_b = slugify(profile_b.get("username") or id2) if profile_b else id2
        compare_path = f"/compare/{slug_a}-{id1}-vs-{slug_b}-{id2}"
        await store_request("comparison", name, url1, url2, status="fulfilled")
        from urllib.parse import quote
        return RedirectResponse(f"/?exists_comparison={quote(compare_path, safe='/')}", 303)

    await store_request("comparison", name, url1, url2)
    return RedirectResponse("/?success=comparison", 303)


@app.get("/admin/stats", response_class=HTMLResponse)
async def admin_stats(request: Request):
    data, pending = await asyncio.gather(get_analytics(), get_pending_requests())
    return templates.TemplateResponse("admin.html", {"request": request, "pending_requests": pending, **data})


@app.get("/health")
async def health():
    return {"status": "ok"}
