# Diary — AI-Augmented Personal Life Log

Single-user, open-source diary app. Python end-to-end (no JavaScript authored
by hand — only HTMX from CDN and a minimal service worker for PWA install).

## Stack

- **Backend:** FastAPI + SQLAlchemy 2.0, SQLite (+ sqlite-vec when available)
- **Frontend:** Jinja2 templates + HTMX, single CSS file, PWA
- **AI:** Anthropic Claude API ↔ local Ollama, toggled at runtime from the UI
- **Embeddings:** Ollama `nomic-embed-text`, stored as float32 BLOBs
- **PDF export:** fpdf2 with core fonts only — day/month/all/topic downloads
  under `/export/`, plus topic summaries and coach sessions rendered from
  the same markdown the web UI shows

## Run

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
# .env must exist with ALLOWED_EMAIL and a random SECRET_KEY —
# the app refuses to start without them (see backend/config.py)
python run.py                                     # http://localhost:8000
```

## Critical invariants — do not break

1. **Single-user gatekeeper.** The repo is public. Every request passes through
   `backend/auth.py:GatekeeperMiddleware`; only `ALLOWED_EMAIL` may hold a
   session, all others get 403. Never add a route that bypasses this without
   adding it to `PUBLIC_PATHS` deliberately.
2. **Secrets stay in `.env`** (gitignored). Never hardcode keys; never commit
   `.env` or `data/`. There is deliberately no `.env.example` — config.py
   documents every variable and fails fast on missing/insecure values.
3. **AUTH_MODE=dev** auto-logs-in the owner, and is honored ONLY for loopback
   connections (see `auth._is_local`) — remote clients always hit OAuth.
4. **Security headers** (CSP, frame-deny, nosniff, HSTS-on-https) are attached
   by the gatekeeper middleware to every response, including public paths.
   htmx is the only external script, SRI-pinned to unpkg.

## Layout

- `backend/` — API, models, auth, AI services → see `backend/CLAUDE.md`
- `frontend/` — templates, CSS, PWA assets → see `frontend/CLAUDE.md`
- `run.py` — uvicorn entry point
- `data/diary.db` — SQLite database (created on first run, gitignored)

## Conventions

- HTMX endpoints return HTML partials from `frontend/templates/partials/`,
  not JSON. JSON is reserved for future programmatic API needs.
- AI failures must degrade gracefully: entries always save even if
  polish/embedding fails; errors render inline in the affected partial.
- AI output that should survive restarts (weekly reviews, topic summaries,
  coach sessions, the coach's profile memory) is cached in `Setting` rows —
  see the key namespaces in `backend/CLAUDE.md`. Regenerating overwrites.
- Topics: six presets (Work, Personal, Discovery, Growth, Failure, Struggle)
  are seeded at startup; users add custom ones from the new-entry form.
- Keep all code Python. Do not introduce Node, npm, or hand-written JS.
