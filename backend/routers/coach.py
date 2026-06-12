"""Monthly AI coach. The coach keeps persistent profile notes about the user
(Setting "coach:profile"), reads a whole month of entries, and writes a
coaching session (cached per month in Setting "coach:YYYY-MM"). After each
session it updates its own notes — that's the "remembers who you are" part."""
import calendar as cal
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Entry, Setting
from ..services import ai
from ..templating import templates

router = APIRouter()

PROFILE_KEY = "coach:profile"
MAX_ENTRY_CHARS = 2500


def _parse_ym(ym: str | None) -> tuple[int, int]:
    today = date.today()
    if not ym:
        return today.year, today.month
    try:
        year, month = map(int, ym.split("-"))
        date(year, month, 1)  # validates
        return year, month
    except ValueError:
        return today.year, today.month


def _month_entries(db: Session, year: int, month: int) -> list[Entry]:
    first = date(year, month, 1)
    last = date(year, month, cal.monthrange(year, month)[1])
    return (
        db.query(Entry)
        .filter(Entry.entry_date >= first, Entry.entry_date <= last)
        .order_by(Entry.entry_date, Entry.created_at)
        .all()
    )


def _mood_summary(entries: list[Entry]) -> str:
    """The emotional shape of the month, computed so the coach can set its
    register (comfort vs. push) instead of guessing from prose."""
    by_day: dict[date, list[int]] = {}
    for e in entries:
        if e.mood:
            by_day.setdefault(e.entry_date, []).append(e.mood)
    if not by_day:
        return ""
    day_avgs = {d: sum(m) / len(m) for d, m in sorted(by_day.items())}
    avg = sum(day_avgs.values()) / len(day_avgs)
    rough = [d for d, v in day_avgs.items() if v <= 2]
    great = [d for d, v in day_avgs.items() if v >= 4]

    lines = [
        f"{len(day_avgs)} of the month's days have mood scores. Average {avg:.1f}/5.",
        "Rough days (mood <= 2): "
        + (", ".join(d.strftime("%B %d") for d in rough) if rough else "none"),
        "Great days (mood >= 4): "
        + (", ".join(d.strftime("%B %d") for d in great) if great else "none"),
    ]
    if len(day_avgs) >= 4:
        days = list(day_avgs)
        half = len(days) // 2
        first = sum(day_avgs[d] for d in days[:half]) / half
        second = sum(day_avgs[d] for d in days[half:]) / (len(days) - half)
        trend = "improving" if second - first > 0.3 else "declining" if first - second > 0.3 else "steady"
        lines.append(f"Trend across the month: {trend} (first half {first:.1f}, second half {second:.1f}).")
    return "\n".join(lines)


def _prev_session(db: Session, year: int, month: int) -> str:
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    return _get(db, f"coach:{prev_y:04d}-{prev_m:02d}") or ""


def _corpus(entries: list[Entry]) -> str:
    return "\n\n".join(
        f"[{e.entry_date.isoformat()}] {e.title}"
        + (f" (topic: {e.topic.name})" if e.topic else "")
        + (f" (mood {e.mood}/5)" if e.mood else "")
        + f"\n{e.display_text[:MAX_ENTRY_CHARS]}"
        for e in entries
    )


def _get(db: Session, key: str) -> str | None:
    row = db.get(Setting, key)
    return row.value if row else None


def _put(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))


@router.get("/coach", response_class=HTMLResponse)
async def coach_page(request: Request, ym: str | None = None, db: Session = Depends(get_db)):
    year, month = _parse_ym(ym)
    today = date.today()
    first = date(year, month, 1)
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return templates.TemplateResponse(
        request,
        "coach.html",
        {
            "active": "coach",
            "provider": ai.get_provider(db),
            "ym": f"{year:04d}-{month:02d}",
            "month_label": first.strftime("%B %Y"),
            "prev_ym": f"{prev_y:04d}-{prev_m:02d}",
            "next_ym": f"{next_y:04d}-{next_m:02d}" if date(next_y, next_m, 1) <= today else None,
            "entry_count": len(_month_entries(db, year, month)),
            "advice": _get(db, f"coach:{year:04d}-{month:02d}"),
            "profile": _get(db, PROFILE_KEY),
        },
    )


@router.post("/api/coach", response_class=HTMLResponse)
async def coach_session(request: Request, ym: str = Form(...), db: Session = Depends(get_db)):
    year, month = _parse_ym(ym)
    month_label = date(year, month, 1).strftime("%B %Y")

    def fail(msg: str):
        return templates.TemplateResponse(
            request, "partials/coach_body.html",
            {"error": msg, "month_label": month_label},
        )

    entries = _month_entries(db, year, month)
    if not entries:
        return fail(f"No entries in {month_label} — the coach needs something to read.")

    corpus = _corpus(entries)
    profile = _get(db, PROFILE_KEY) or ""
    try:
        advice = await ai.coach_advice(
            db, profile, month_label, corpus,
            mood_summary=_mood_summary(entries),
            last_session=_prev_session(db, year, month),
        )
    except Exception as exc:
        return fail(str(exc))

    _put(db, f"coach:{year:04d}-{month:02d}", advice)
    db.commit()

    # Memory update is best-effort: the session is already saved.
    new_profile = None
    try:
        new_profile = await ai.coach_update_profile(db, profile, corpus)
        _put(db, PROFILE_KEY, new_profile)
        db.commit()
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "partials/coach_body.html",
        {"advice": advice, "month_label": month_label, "oob_profile": new_profile},
    )
