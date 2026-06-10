"""Openable month calendar: entries, reminders, public holidays, moods."""
import calendar as cal
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Entry, Reminder
from ..services import ai, external
from ..templating import templates

router = APIRouter()

cal.setfirstweekday(cal.MONDAY)


@router.get("/calendar", response_class=HTMLResponse)
async def month_view(
    request: Request,
    y: int | None = None,
    m: int | None = None,
    db: Session = Depends(get_db),
):
    today = date.today()
    year, month = y or today.year, m or today.month

    first = date(year, month, 1)
    last = date(year, month, cal.monthrange(year, month)[1])

    entries = (
        db.query(Entry)
        .filter(Entry.entry_date >= first, Entry.entry_date <= last)
        .all()
    )
    by_day: dict[date, list[Entry]] = defaultdict(list)
    for e in entries:
        by_day[e.entry_date].append(e)

    reminder_days = {
        r.due_date
        for r in db.query(Reminder)
        .filter(Reminder.due_date >= first, Reminder.due_date <= last, Reminder.done.is_(False))
        .all()
    }

    hols = await external.holidays(year)

    weeks = []
    for week in cal.monthcalendar(year, month):
        row = []
        for daynum in week:
            if daynum == 0:
                row.append(None)
                continue
            d = date(year, month, daynum)
            day_entries = by_day.get(d, [])
            moods = [e.mood for e in day_entries if e.mood]
            row.append({
                "date": d,
                "count": len(day_entries),
                "has_reminders": d in reminder_days,
                "holiday": hols.get(d.isoformat()),
                "mood": round(sum(moods) / len(moods)) if moods else None,
            })
        weeks.append(row)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            "active": "calendar",
            "provider": ai.get_provider(db),
            "year": year,
            "month_name": first.strftime("%B"),
            "weeks": weeks,
            "today": today,
            "prev_y": prev_y, "prev_m": prev_m,
            "next_y": next_y, "next_m": next_m,
            "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        },
    )
