"""PDF downloads: one day, one month, everything, or one topic (with its
cached AI summary as a cover section). Protected by the gatekeeper like
every other route."""
import calendar as cal
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Entry, Setting, Topic
from ..services import pdf

router = APIRouter(prefix="/export")


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _by_day(entries: list[Entry]) -> list[tuple[str, list[Entry]]]:
    grouped: dict[date, list[Entry]] = defaultdict(list)
    for e in entries:
        grouped[e.entry_date].append(e)
    return [(d.strftime("%A, %B %d"), grouped[d]) for d in sorted(grouped)]


@router.get("/day/{day}.pdf")
async def day_pdf(day: str, db: Session = Depends(get_db)):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "Bad date")
    entries = db.query(Entry).filter(Entry.entry_date == d).order_by(Entry.created_at).all()
    content = pdf.entries_pdf(
        d.strftime("%A, %B %d, %Y"),
        f"Diary - {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
        [("", entries)],
    )
    return _pdf_response(content, f"diary-{day}.pdf")


@router.get("/month/{year}/{month}.pdf")
async def month_pdf(year: int, month: int, db: Session = Depends(get_db)):
    if not 1 <= month <= 12:
        raise HTTPException(400, "Bad month")
    first = date(year, month, 1)
    last = date(year, month, cal.monthrange(year, month)[1])
    entries = (
        db.query(Entry)
        .filter(Entry.entry_date >= first, Entry.entry_date <= last)
        .order_by(Entry.entry_date, Entry.created_at)
        .all()
    )
    content = pdf.entries_pdf(
        first.strftime("%B %Y"),
        f"Diary - {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
        _by_day(entries),
    )
    return _pdf_response(content, f"diary-{year}-{month:02d}.pdf")


@router.get("/all.pdf")
async def all_pdf(db: Session = Depends(get_db)):
    entries = db.query(Entry).order_by(Entry.entry_date, Entry.created_at).all()
    grouped: dict[str, list[Entry]] = defaultdict(list)
    for e in entries:
        grouped[e.entry_date.strftime("%B %Y")].append(e)
    content = pdf.entries_pdf(
        "Diary - complete archive",
        f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
        list(grouped.items()),
    )
    return _pdf_response(content, "diary-all.pdf")


@router.get("/topic/{topic_id}.pdf")
async def topic_pdf(topic_id: int, scope: str = "all", db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(404)
    q = db.query(Entry).filter(Entry.topic_id == topic_id)
    if scope != "all":  # scope is "YYYY-MM"
        try:
            year, month = map(int, scope.split("-"))
            first = date(year, month, 1)
            last = date(year, month, cal.monthrange(year, month)[1])
        except ValueError:
            raise HTTPException(400, "Bad scope")
        q = q.filter(Entry.entry_date >= first, Entry.entry_date <= last)
        period = first.strftime("%B %Y")
    else:
        period = "all time"
    entries = q.order_by(Entry.entry_date, Entry.created_at).all()

    cached = db.get(Setting, f"topic-summary:{topic_id}:{scope}")
    content = pdf.entries_pdf(
        f"Topic: {topic.name}",
        f"{period} - {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}",
        _by_day(entries),
        intro_heading="AI summary" if cached else "",
        intro_md=cached.value if cached else "",
    )
    return _pdf_response(content, f"diary-topic-{topic.name.lower().replace(' ', '-')}-{scope}.pdf")
