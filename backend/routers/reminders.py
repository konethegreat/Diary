"""Native reminders/tasks attached to the daily view."""
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Reminder
from ..templating import templates

router = APIRouter()


def _list(db: Session, day: date) -> list[Reminder]:
    return (
        db.query(Reminder)
        .filter(Reminder.due_date <= day)
        .order_by(Reminder.done, Reminder.due_date)
        .all()
    )


@router.get("/api/reminders", response_class=HTMLResponse)
async def list_reminders(request: Request, d: str | None = None, db: Session = Depends(get_db)):
    day = date.fromisoformat(d) if d else date.today()
    return templates.TemplateResponse(
        request, "partials/reminder_list.html", {"reminders": _list(db, day), "day": day}
    )


@router.post("/api/reminders", response_class=HTMLResponse)
async def add_reminder(
    request: Request,
    text: str = Form(...),
    due_date: str = Form(...),
    db: Session = Depends(get_db),
):
    day = date.fromisoformat(due_date)
    db.add(Reminder(text=text.strip(), due_date=day))
    db.commit()
    return templates.TemplateResponse(
        request, "partials/reminder_list.html", {"reminders": _list(db, day), "day": day}
    )


@router.post("/api/reminders/{rid}/toggle", response_class=HTMLResponse)
async def toggle_reminder(rid: int, request: Request, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if r:
        r.done = not r.done
        db.commit()
    day = r.due_date if r else date.today()
    return templates.TemplateResponse(
        request, "partials/reminder_list.html", {"reminders": _list(db, date.today()), "day": day}
    )


@router.delete("/api/reminders/{rid}", response_class=HTMLResponse)
async def delete_reminder(rid: int, request: Request, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if r:
        db.delete(r)
        db.commit()
    return templates.TemplateResponse(
        request, "partials/reminder_list.html", {"reminders": _list(db, date.today()), "day": date.today()}
    )
