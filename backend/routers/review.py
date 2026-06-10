"""AI weekly review: reflection over the last 7 days, cached per ISO week."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Entry, Setting
from ..services import ai
from ..templating import templates

router = APIRouter()


def _week_key(today: date) -> str:
    iso = today.isocalendar()
    return f"review:{iso.year}-W{iso.week:02d}"


def _week_entries(db: Session, today: date) -> list[Entry]:
    start = today - timedelta(days=6)
    return (
        db.query(Entry)
        .filter(Entry.entry_date >= start, Entry.entry_date <= today)
        .order_by(Entry.entry_date)
        .all()
    )


def _mood_days(entries: list[Entry], today: date) -> list[dict]:
    by_day: dict[date, list[int]] = {}
    for e in entries:
        if e.mood:
            by_day.setdefault(e.entry_date, []).append(e.mood)
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        moods = by_day.get(d)
        days.append({
            "date": d,
            "mood": round(sum(moods) / len(moods)) if moods else None,
        })
    return days


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    entries = _week_entries(db, today)
    cached = db.get(Setting, _week_key(today))
    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "active": "review",
            "provider": ai.get_provider(db),
            "mood_days": _mood_days(entries, today),
            "entry_count": len(entries),
            "review": cached.value if cached else None,
        },
    )


@router.post("/api/review", response_class=HTMLResponse)
async def generate_review(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    entries = _week_entries(db, today)
    if not entries:
        return templates.TemplateResponse(
            request, "partials/review_body.html",
            {"review": None, "error": "No entries in the last 7 days — write something first."},
        )
    corpus = "\n\n".join(
        f"[{e.entry_date.isoformat()}] {e.title}"
        + (f" (mood {e.mood}/5)" if e.mood else "")
        + f"\n{e.display_text}"
        for e in entries
    )
    try:
        text = await ai.weekly_review(db, corpus)
    except Exception as exc:
        return templates.TemplateResponse(
            request, "partials/review_body.html", {"review": None, "error": str(exc)}
        )
    key = _week_key(today)
    row = db.get(Setting, key)
    if row:
        row.value = text
    else:
        db.add(Setting(key=key, value=text))
    db.commit()
    return templates.TemplateResponse(
        request, "partials/review_body.html", {"review": text, "error": None}
    )
