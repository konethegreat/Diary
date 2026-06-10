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


COACH_SYSTEM = """You are the user's long-term personal coach. You have two
inputs: your private profile notes about them (built up over previous months)
and their diary entries for one month. Write their monthly coaching session in
markdown: 1) a warm, candid 3–4 sentence reflection on the month that shows you
know who they are, 2) **Patterns** — what kept showing up, good and bad,
3) **Advice** — 2–3 concrete, specific recommendations tied to what they wrote,
4) **One challenge** for next month, small and measurable. Speak directly to
them ("you"). Quote dates when referencing entries. Max ~350 words."""


async def coach_advice(db: Session, profile: str, month_label: str, corpus: str) -> str:
    prompt = (
        f"Profile notes so far:\n{profile or '(first session — no notes yet)'}\n\n"
        f"Month: {month_label}\n\nDiary entries:\n\n{corpus}"
    )
    return await complete(db, COACH_SYSTEM, prompt, max_tokens=1000)


COACH_PROFILE_SYSTEM = """You maintain compact private profile notes about a
diary author for their personal coach. Merge the existing notes with what this
month's entries reveal: who they are, what they're working toward, recurring
struggles, wins, habits, people and projects that matter. Drop stale details,
keep it under 200 words, plain prose. Return ONLY the updated notes."""


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
