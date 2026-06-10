"""Morning brief endpoint — also callable by external cron if desired."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import brief as brief_service
from ..templating import templates

router = APIRouter()


@router.get("/api/brief", response_class=HTMLResponse)
async def get_brief(request: Request, force: bool = False, db: Session = Depends(get_db)):
    try:
        content = await brief_service.generate(db, force=force)
        error = None
    except Exception as exc:
        content, error = "", str(exc)
    return templates.TemplateResponse(
        request, "partials/brief.html", {"content": content, "error": error}
    )
