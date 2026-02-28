import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from server.database import close_pool, get_recent_profiles, init_pool
from server.routers import comparisons, profiles

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(title="Shelf Aware", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.state.templates = templates

app.include_router(profiles.router)
app.include_router(comparisons.router)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    recent = await get_recent_profiles(limit=12)
    return templates.TemplateResponse(
        "home.html", {"request": request, "recent": recent, "error": None}
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
