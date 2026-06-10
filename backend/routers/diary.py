"""Diary pages + entry CRUD + AI polish. HTMX returns partials."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import extract

from ..database import get_db
from ..models import Entry, Topic
from ..services import ai, embeddings, external
from ..templating import templates

router = APIRouter()


def _on_this_day(db: Session, day: date) -> list[Entry]:
    """Entries from the same calendar date in previous years."""
    return (
        db.query(Entry)
        .filter(
            extract("month", Entry.entry_date) == day.month,
            extract("day", Entry.entry_date) == day.day,
            Entry.entry_date < date(day.year, 1, 1),
        )
        .order_by(Entry.entry_date.desc())
        .limit(3)
        .all()
    )


async def _day_context(db: Session, day: date) -> dict:
    today = date.today()
    hols = await external.holidays(day.year)
    return {
        "day": day,
        "prev_day": day - timedelta(days=1),
        "next_day": day + timedelta(days=1),
        "today": today,
        "entries": db.query(Entry).filter(Entry.entry_date == day).order_by(Entry.created_at).all(),
        "topics": db.query(Topic).order_by(Topic.name).all(),
        "provider": ai.get_provider(db),
        "weather": await external.todays_weather() if day == today else None,
        "quote": await external.daily_quote() if day == today else None,
        "holiday": hols.get(day.isoformat()),
        "memories": _on_this_day(db, day),
    }


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, d: str | None = None, db: Session = Depends(get_db)):
    day = date.fromisoformat(d) if d else date.today()
    ctx = await _day_context(db, day)
    return templates.TemplateResponse(request, "diary.html", {"active": "diary", **ctx})


@router.post("/api/entries", response_class=HTMLResponse)
async def create_entry(
    request: Request,
    title: str = Form(""),
    raw_text: str = Form(...),
    topic_id: str = Form(""),
    entry_date: str = Form(...),
    db: Session = Depends(get_db),
):
    entry = Entry(
        title=title.strip() or "Untitled",
        raw_text=raw_text.strip(),
        topic_id=int(topic_id) if topic_id else None,
        entry_date=date.fromisoformat(entry_date),
    )
    db.add(entry)
    db.commit()
    await embeddings.embed_entry(entry, db)  # best-effort; entry saves regardless
    return templates.TemplateResponse(request, "partials/entry_card.html", {"e": entry})


@router.post("/api/entries/{entry_id}/polish", response_class=HTMLResponse)
async def polish_entry(entry_id: int, request: Request, db: Session = Depends(get_db)):
    entry = db.get(Entry, entry_id)
    if not entry:
        raise HTTPException(404)
    try:
        entry.polished_text = await ai.polish(db, entry.raw_text)
    except Exception as exc:  # surface provider errors in the card
        return templates.TemplateResponse(
            request, "partials/entry_card.html", {"e": entry, "error": str(exc)}
        )
    entry.mood = await ai.mood_score(db, entry.raw_text) or entry.mood
    db.commit()
    await embeddings.embed_entry(entry, db)
    return templates.TemplateResponse(request, "partials/entry_card.html", {"e": entry})


@router.delete("/api/entries/{entry_id}", response_class=HTMLResponse)
async def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(Entry, entry_id)
    if entry:
        db.delete(entry)
        db.commit()
    return HTMLResponse("")


@router.post("/api/topics", response_class=HTMLResponse)
async def create_topic(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    if name and not db.query(Topic).filter(Topic.name == name).first():
        db.add(Topic(name=name))
        db.commit()
    topics = db.query(Topic).order_by(Topic.name).all()
    return templates.TemplateResponse(request, "partials/topic_options.html", {"topics": topics})


@router.post("/api/provider", response_class=HTMLResponse)
async def toggle_provider(request: Request, db: Session = Depends(get_db)):
    new = "local" if ai.get_provider(db) == "anthropic" else "anthropic"
    ai.set_provider(db, new)
    return templates.TemplateResponse(request, "partials/provider_toggle.html", {"provider": new})
