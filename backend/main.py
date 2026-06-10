"""App assembly: middleware, routers, PWA files, theme, daily brief scheduler."""
from contextlib import asynccontextmanager

import markdown as md
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from .auth import GatekeeperMiddleware, router as auth_router
from .config import settings
from .database import SessionLocal, init_db
from .routers import brief, calendar_view, chat, diary, reminders, review
from .services import brief as brief_service
from .templating import templates

MOOD_EMOJI = {1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}


async def _scheduled_brief() -> None:
    db = SessionLocal()
    try:
        await brief_service.generate(db, force=True)
    except Exception:
        pass  # provider offline — UI will generate on demand
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_scheduled_brief, CronTrigger(hour=settings.BRIEF_HOUR, minute=0))
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Diary", lifespan=lifespan)

# Order matters: SessionMiddleware (added last = outermost) must run before
# the gatekeeper, which reads the session on every request.
app.add_middleware(GatekeeperMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    max_age=60 * 60 * 24 * 30,  # 30 days
    https_only=False,  # cookie Secure flag is added by the proxy when serving HTTPS
)

app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")

templates.env.filters["markdown"] = lambda text: md.markdown(text or "", extensions=["nl2br"])
templates.env.globals["MOOD_EMOJI"] = MOOD_EMOJI

app.include_router(auth_router)
app.include_router(diary.router)
app.include_router(chat.router)
app.include_router(reminders.router)
app.include_router(brief.router)
app.include_router(calendar_view.router)
app.include_router(review.router)


@app.post("/api/theme")
async def toggle_theme(request: Request):
    """Flip light/dark. Stored in a cookie; HTMX refreshes the page."""
    current = request.cookies.get("theme", "dark")
    new = "light" if current == "dark" else "dark"
    resp = Response(status_code=204, headers={"HX-Refresh": "true"})
    resp.set_cookie("theme", new, max_age=60 * 60 * 24 * 365, samesite="lax")
    return resp


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("email") == settings.ALLOWED_EMAIL:
        from starlette.responses import RedirectResponse

        return RedirectResponse("/")
    return templates.TemplateResponse(request, "login.html", {})


# PWA files served from the root scope
@app.get("/manifest.json", include_in_schema=False)
async def manifest():
    return FileResponse(settings.STATIC_DIR / "manifest.json")


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(settings.STATIC_DIR / "sw.js", media_type="application/javascript")
