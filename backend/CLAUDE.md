# Backend — FastAPI

## Map

| File | Purpose |
|---|---|
| `main.py` | App assembly: middleware order, routers, PWA routes, brief scheduler |
| `config.py` | All settings from `.env`; the only place env vars are read |
| `auth.py` | Google OAuth + **GatekeeperMiddleware** (single-user 403 wall) |
| `database.py` | Engine, sessions, sqlite-vec loading, `init_db()` |
| `models.py` | Topic, Entry, Reminder, Setting, Brief |
| `routers/diary.py` | Pages + entry CRUD + polish (+ mood) + provider toggle |
| `routers/chat.py` | RAG chat endpoint |
| `routers/reminders.py` | Reminder CRUD |
| `routers/brief.py` | Morning brief endpoint |
| `routers/calendar_view.py` | Month calendar: entries, reminders, holidays, moods |
| `routers/review.py` | AI weekly review, cached per ISO week in Setting rows |
| `routers/topics.py` | Topics page + per-topic AI summaries (cached per topic+period) |
| `routers/coach.py` | Monthly AI coach: mood-aware sessions, persistent profile, follow-ups |
| `routers/export.py` | PDF downloads: `/export/{day,month,all,topic}` |
| `services/ai.py` | Provider abstraction (`complete()`), polish/chat/mood/review/topic/coach prompts |
| `services/pdf.py` | fpdf2 PDF builder — latin-1 core fonts, entry markdown via `write_html` |
| `services/embeddings.py` | Embed via Ollama, pack/unpack BLOBs, cosine search |
| `services/brief.py` | Morning brief agent (weather + holidays + reminders + yesterday) |
| `services/notify.py` | Phone push via ntfy.sh — best-effort, no-op without NTFY_TOPIC |
| `services/external.py` | Keyless APIs: Open-Meteo, Nager.Date, ZenQuotes — all best-effort |
| `services/calendar_stub.py` | Replace with Google Calendar / MS Graph |

## Rules

- **Middleware order in `main.py` is load-bearing**: SessionMiddleware is added
  last so it runs *before* GatekeeperMiddleware, which reads the session.
- New protected routes need nothing extra — the gatekeeper covers everything
  not in `auth.PUBLIC_PATHS` / `PUBLIC_PREFIXES`.
- Provider routing: never call Anthropic/Ollama directly from routers; go
  through `services/ai.complete()` so the UI toggle keeps working.
- Embeddings are best-effort: `embed_entry()` returns False when Ollama is
  down and the caller must continue. Don't make saving depend on it.
- DB sessions come from `Depends(get_db)`; background jobs create their own
  `SessionLocal()` and must close it.
- The `Setting` table doubles as the AI cache. Key namespaces in use:
  `ai_provider`, `review:{ISO-week}`, `topic-summary:{topic_id}:{YYYY-MM|all}`,
  `coach:{YYYY-MM}`, `coach:profile` (the coach's persistent memory of the
  user, rewritten by the model after every session). Don't reuse these prefixes.
- Preset topics (Work, Personal, Discovery, Growth, Failure, Struggle) are
  seeded idempotently by `database.init_db()`; custom topics come from the UI.
- **The coach is deliberately not generic.** `routers/coach.py` computes the
  month's emotional shape (`_mood_summary`: avg mood, rough/great days, trend)
  and passes it plus last month's session into the prompt. The prompt contract:
  comfort-first after rough months (no criticism), push harder after strong
  ones, quote the user's own entries with dates, follow up on last month's
  challenge. The profile memory has two parts — who they are, and "what lifts
  them" (dated wins to recall on hard days). Preserve this contract when
  touching coach prompts.
- PDF exports must never 500 on content: `services/pdf.py` sanitizes
  everything to latin-1 (emoji are dropped) — keep it that way rather than
  adding font files.

## Extending

- **Real calendar:** implement `services/calendar_stub.todays_events()` —
  return `["09:00–09:30 Standup", ...]` strings and the brief + agenda UI
  pick it up unchanged.
- **External cron for the brief:** `GET /api/brief?force=true` (authenticated)
  regenerates; the in-process APScheduler job already runs at `BRIEF_HOUR`.
