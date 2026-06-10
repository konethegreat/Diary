"""The Morning Brief agent.

Gathers today's calendar events (stub until Google/Microsoft Graph is wired),
open reminders, and yesterday's diary entries, then asks the active AI
provider for a conversational brief. Cached one per day in the briefs table.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import Brief, Entry, Reminder
from . import ai, external
from .calendar_stub import todays_events

BRIEF_SYSTEM = """You are a sharp, friendly personal chief-of-staff. Write a short
conversational morning brief in markdown: greet briefly, then lay out today's
priorities based on the calendar, open reminders, and what was accomplished or
left unfinished yesterday. Be specific, skip filler, max ~200 words."""


async def generate(db: Session, force: bool = False) -> str:
    today = date.today()
    cached = db.get(Brief, today)
    if cached and not force:
        return cached.content

    yesterday = today - timedelta(days=1)
    entries = db.query(Entry).filter(Entry.entry_date == yesterday).all()
    reminders = db.query(Reminder).filter(Reminder.done.is_(False), Reminder.due_date <= today).all()
    events = todays_events()
    weather = await external.todays_weather()
    hols = await external.holidays(today.year)
    holiday = hols.get(today.isoformat())

    weather_line = (
        f"Weather: {weather['label']}, {weather['temp_min']}–{weather['temp_max']}°C.\n"
        if weather else ""
    )
    holiday_line = f"Today is a public holiday: {holiday}.\n" if holiday else ""

    prompt = (
        f"Today is {today.strftime('%A, %B %d, %Y')}.\n"
        + weather_line + holiday_line + "\n"
        f"Calendar events today:\n"
        + ("\n".join(f"- {e}" for e in events) if events else "- (none)")
        + "\n\nOpen reminders:\n"
        + ("\n".join(f"- {r.text} (due {r.due_date})" for r in reminders) if reminders else "- (none)")
        + "\n\nYesterday's diary:\n"
        + ("\n\n".join(f"{e.title}\n{e.display_text}" for e in entries) if entries else "(no entries)")
    )

    content = await ai.complete(db, BRIEF_SYSTEM, prompt, max_tokens=600)

    if cached:
        cached.content = content
    else:
        db.add(Brief(brief_date=today, content=content))
    db.commit()
    return content
