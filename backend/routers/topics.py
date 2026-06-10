"""Topics page: preset + custom topics, per-topic AI summaries (cached in
Setting rows keyed by topic + period), PDF download links."""
import calendar as cal
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Entry, Setting, Topic
from ..services import ai
from ..templating import templates

router = APIRouter()

MAX_ENTRIES = 200       # cap the corpus for all-time summaries
MAX_ENTRY_CHARS = 2500


def _topic_rows(db: Session) -> list[dict]:
    counts = dict(db.query(Entry.topic_id, func.count()).group_by(Entry.topic_id).all())
    return [
        {"t": t, "count": counts.get(t.id, 0)}
        for t in db.query(Topic).order_by(Topic.name).all()
    ]


def _corpus(entries: list[Entry]) -> str:
    return "\n\n".join(
        f"[{e.entry_date.isoformat()}] {e.title}"
        + (f" (mood {e.mood}/5)" if e.mood else "")
        + f"\n{e.display_text[:MAX_ENTRY_CHARS]}"
        for e in entries
    )


@router.get("/topics", response_class=HTMLResponse)
async def topics_page(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    prev_y, prev_m = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
    return templates.TemplateResponse(
        request,
        "topics.html",
        {
            "active": "topics",
            "provider": ai.get_provider(db),
            "rows": _topic_rows(db),
            "month_value": today.strftime("%Y-%m"),
            "month_label": today.strftime("%B %Y"),
            "last_month_value": f"{prev_y:04d}-{prev_m:02d}",
            "last_month_label": date(prev_y, prev_m, 1).strftime("%B %Y"),
        },
    )


@router.post("/api/topics/summary", response_class=HTMLResponse)
async def summarize_topic(
    request: Request,
    topic_id: int = Form(...),
    scope: str = Form("all"),
    db: Session = Depends(get_db),
):
    def fail(msg: str):
        return templates.TemplateResponse(
            request, "partials/topic_summary.html", {"error": msg}
        )

    topic = db.get(Topic, topic_id)
    if not topic:
        return fail("Topic not found.")

    q = db.query(Entry).filter(Entry.topic_id == topic_id)
    if scope == "all":
        period_label = "all time"
    else:
        try:
            year, month = map(int, scope.split("-"))
            first = date(year, month, 1)
            last = date(year, month, cal.monthrange(year, month)[1])
        except ValueError:
            return fail("Bad period.")
        q = q.filter(Entry.entry_date >= first, Entry.entry_date <= last)
        period_label = first.strftime("%B %Y")

    entries = q.order_by(Entry.entry_date, Entry.created_at).all()[-MAX_ENTRIES:]
    if not entries:
        return fail(f"No {topic.name} entries for {period_label} — tag some entries with this topic first.")

    try:
        text = await ai.topic_summary(db, topic.name, period_label, _corpus(entries))
    except Exception as exc:
        return fail(str(exc))

    key = f"topic-summary:{topic_id}:{scope}"
    row = db.get(Setting, key)
    if row:
        row.value = text
    else:
        db.add(Setting(key=key, value=text))
    db.commit()

    return templates.TemplateResponse(
        request,
        "partials/topic_summary.html",
        {"summary": text, "topic": topic, "scope": scope, "period_label": period_label},
    )
