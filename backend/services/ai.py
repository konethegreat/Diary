"""AI provider abstraction.

Two providers behind one `complete()` call:
  - "anthropic": Claude API (use on mobile / away from desk)
  - "local":     Ollama at OLLAMA_BASE_URL (use at your desk, zero API cost)

The active provider is a Setting row ("ai_provider") toggled from the UI.
"""
import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Setting

PROVIDER_KEY = "ai_provider"
DEFAULT_PROVIDER = "anthropic"


def get_provider(db: Session) -> str:
    row = db.get(Setting, PROVIDER_KEY)
    return row.value if row else DEFAULT_PROVIDER


def set_provider(db: Session, provider: str) -> str:
    if provider not in ("anthropic", "local"):
        raise ValueError("provider must be 'anthropic' or 'local'")
    row = db.get(Setting, PROVIDER_KEY)
    if row:
        row.value = provider
    else:
        db.add(Setting(key=PROVIDER_KEY, value=provider))
    db.commit()
    return provider


async def complete(db: Session, system: str, prompt: str, max_tokens: int = 1500) -> str:
    """Route a completion to the active provider."""
    provider = get_provider(db)
    if provider == "local":
        return await _ollama_complete(system, prompt)
    return await _anthropic_complete(system, prompt, max_tokens)


async def _anthropic_complete(system: str, prompt: str, max_tokens: int) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — add it to .env or toggle to the local provider.")
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": settings.ANTHROPIC_MODEL,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        r.raise_for_status()
        return r.json()["content"][0]["text"]


async def _ollama_complete(system: str, prompt: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json={
                "model": settings.OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


# ---------------------------------------------------------------- prompts ---

POLISH_SYSTEM = """You are a precise writing assistant for a personal work diary.
The user brain-dumps messy, unformatted notes about their day. Rewrite them:
- Fix grammar and structure; keep the author's voice and first person.
- Summarize technical work concisely and accurately — do not invent details.
- Use short markdown: a bold one-line summary, then tight bullet points grouped
  by theme if there are several.
Return ONLY the polished text, no preamble."""


async def polish(db: Session, raw_text: str) -> str:
    return await complete(db, POLISH_SYSTEM, raw_text)


MOOD_SYSTEM = """Rate the overall mood of this diary entry on a scale of 1 to 5:
1 = rough day, 2 = below average, 3 = neutral, 4 = good, 5 = great.
Respond with ONLY the single digit, nothing else."""


async def mood_score(db: Session, text: str) -> int | None:
    """Best-effort 1–5 mood rating. Returns None on any failure."""
    try:
        raw = await complete(db, MOOD_SYSTEM, text, max_tokens=4)
        score = int(raw.strip()[0])
        return score if 1 <= score <= 5 else None
    except Exception:
        return None


REVIEW_SYSTEM = """You are a thoughtful personal coach reviewing someone's diary.
Given the past week's entries (with mood scores where available), write a short
markdown "weekly review": 1) a warm 2–3 sentence overview of the week,
2) **Wins** (bullets), 3) **Threads to pick up** — unfinished things worth
returning to, 4) one sharp, kind observation about patterns you notice.
Be specific; quote dates. Max ~250 words."""


async def weekly_review(db: Session, entries_text: str) -> str:
    return await complete(db, REVIEW_SYSTEM, entries_text, max_tokens=800)


TOPIC_SUMMARY_SYSTEM = """You are summarizing one themed section of a personal
diary (e.g. Work, Growth, Failure). Given the entries for that topic, write a
short markdown summary: 1) a 2–3 sentence overview of what this thread of life
looked like in the period, 2) **Highlights** (bullets, quote dates),
3) **Open threads** — things started but not finished, 4) one trend you notice
over time. Be specific and faithful to the entries; never invent. Max ~250 words."""


async def topic_summary(db: Session, topic_name: str, period_label: str, corpus: str) -> str:
    prompt = f"Topic: {topic_name}\nPeriod: {period_label}\n\nEntries:\n\n{corpus}"
    return await complete(db, TOPIC_SUMMARY_SYSTEM, prompt, max_tokens=800)


COACH_SYSTEM = """You are this person's personal coach — THEIR coach, not a
generic one. You are warm, direct, and unmistakably in their corner. You have
known them for months. You receive: (1) your private profile notes built over
previous sessions, (2) last month's session if there was one, (3) the
emotional shape of the month (mood statistics), and (4) the month's entries.

Read the mood data FIRST and let it set your register:
- Rough or stressed month (low average, several rough days, declining trend):
  lead with acknowledgment, not analysis. No criticism, no "areas to improve".
  Show them evidence from their OWN entries that they kept showing up, recall
  a past win from your notes, and set ONE small, gentle challenge. Comfort
  first, momentum second.
- Strong month: celebrate loudly and specifically, then push — they can take
  an ambitious challenge right now.
- Mixed month: honest about both sides, and always end on what's possible.

Your voice:
- Their life is the evidence. Quote their own words back to them with dates
  ("On June 3 you wrote ... — and by June 14 you ..."). Never platitudes,
  never fortune-cookie filler.
- If last month's session set a challenge, follow up on it — kindly if it
  slipped, proudly if it landed.
- Be honest; never invent positives. But never kick them when they're down.
- Speak directly to them ("you"), like someone who has been here all along.

Format in markdown: a heartfelt opening reflection (3–5 sentences), then
**What I saw** — patterns, the good and the hard, **What I want you to
remember** — their own evidence, quoted with dates, **One challenge** — sized
to the month they just had. Max ~400 words."""


async def coach_advice(
    db: Session,
    profile: str,
    month_label: str,
    corpus: str,
    mood_summary: str = "",
    last_session: str = "",
) -> str:
    prompt = (
        f"Your profile notes on them so far:\n{profile or '(first session — no notes yet)'}\n\n"
        f"Last month's session:\n{last_session or '(none — this is the first one)'}\n\n"
        f"Month: {month_label}\n"
        f"Emotional shape of the month:\n{mood_summary or '(no mood scores this month)'}\n\n"
        f"Diary entries:\n\n{corpus}"
    )
    return await complete(db, COACH_SYSTEM, prompt, max_tokens=1200)


COACH_PROFILE_SYSTEM = """You maintain compact private profile notes about a
diary author for their personal coach. Merge the existing notes with what this
month's entries reveal, in two parts:
1) Who they are: what they're working toward, recurring struggles, habits,
   people and projects that matter.
2) What lifts them: concrete past wins the coach can remind them of on hard
   days (with month/date), what has helped them through stress before, and
   what they're proud of.
Drop stale details, keep it under 250 words, plain prose under the two
headings. Return ONLY the updated notes."""


async def coach_update_profile(db: Session, profile: str, corpus: str) -> str:
    prompt = (
        f"Existing notes:\n{profile or '(none yet)'}\n\n"
        f"This month's diary entries:\n\n{corpus}"
    )
    return await complete(db, COACH_PROFILE_SYSTEM, prompt, max_tokens=500)


CHAT_SYSTEM = """You are the user's personal diary assistant. Answer their question
using ONLY the diary excerpts provided as context. Quote dates when referencing
entries. If the context doesn't contain the answer, say so plainly."""


async def chat_with_context(db: Session, question: str, context_blocks: list[str]) -> str:
    ctx = "\n\n---\n\n".join(context_blocks) if context_blocks else "(no relevant entries found)"
    prompt = f"Diary excerpts:\n\n{ctx}\n\n---\n\nQuestion: {question}"
    return await complete(db, CHAT_SYSTEM, prompt)
