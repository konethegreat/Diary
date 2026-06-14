# ✦ Diary — AI-Augmented Personal Life Log

A single-user, installable (PWA) daily diary with AI superpowers. Built almost
entirely in Python (FastAPI + HTMX) — no hand-written JavaScript beyond a tiny
service worker and one helper file. Your entries live in a local SQLite
database on your own machine and never touch the public internet.

> **Source-available, noncommercial.** This project is licensed under the
> PolyForm Noncommercial License 1.0.0 — free to use, modify, and share for
> noncommercial purposes only. See [LICENSE.md](LICENSE.md).

## Features

- **Today** — brain-dump messy notes; one click and AI polishes them into clean
  markdown and scores your mood (1–5). Tag entries with topics, see "on this
  day" memories, and read a daily **morning brief** (weather, holidays, agenda,
  and yesterday's entries woven into your priorities).
- **Topics** — six presets (Work, Personal, Discovery, Growth, Failure,
  Struggle) plus your own custom ones. Get an **AI summary** of any topic over a
  month or all-time — in the app and as a downloadable PDF.
- **Calendar** — month view with entry dots, reminders, holidays, and mood
  emoji.
- **Review** — a weekly AI reflection with a 7-day mood chart.
- **Coach** — a monthly AI coach that *remembers who you are*: it reads the
  month's entries, adapts to your mood (comfort after rough months, a push after
  strong ones), quotes your own words back to you, and follows up on last
  month's challenge.
- **Ask my diary (RAG)** — semantic search over every entry. "What bug did I fix
  in the routing logic last month?" gets a sourced answer.
- **PDF export** — any day, any month, any topic (with its AI summary), or your
  complete archive.
- **Provider toggle** — switch between the Claude API (on the go) and local
  Ollama (at your desk, free, fully private) with one click in the nav bar.
- **Single-user gatekeeper** — the repo can be public; only your email can log
  in (Google OAuth), and everyone else gets a hard 403.

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file in the project root. There is deliberately **no**
`.env.example` — every variable is documented in `backend/config.py`, which
**fails fast** if anything required is missing. At minimum you need:

```dotenv
ALLOWED_EMAIL=you@example.com
SECRET_KEY=<paste a random value>
```

Generate a strong secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then run it:

```bash
python run.py --dev             # → http://localhost:8000
```

For local-only use, `AUTH_MODE=dev` in `.env` skips OAuth and signs you in as
`ALLOWED_EMAIL`. For anything internet-facing, set `AUTH_MODE=oauth` and create
Google OAuth credentials (redirect URI `https://your-host/auth/callback`).

### AI setup

- **Claude:** set `ANTHROPIC_API_KEY`.
- **Local:** install [Ollama](https://ollama.com), then
  `ollama pull llama3.1 && ollama pull nomic-embed-text`.
  Embeddings always use Ollama (free); chat/polish follow the UI toggle.

## Running it on your laptop and phone

The diary is designed to live on your own machine and be reachable from your
phone **without ever being exposed to the public internet**:

- **Laptop:** run `python run.py` as a background/login task. It serves on
  `127.0.0.1:8000` and stores everything in `data/diary.db` locally.
- **Phone:** put the laptop and phone on the same private
  [Tailscale](https://tailscale.com) network and use `tailscale serve` to front
  the local app with HTTPS at a private `https://<device>.<tailnet>.ts.net`
  address. Only your own devices can reach it (Tailscale Funnel stays off).
- **Install as an app:** open the site in Chrome/Edge (desktop or Android) →
  "Install app", or Safari on iOS → Share → "Add to Home Screen". You get a
  home-screen icon, full-screen UI, and an offline app shell.
- **Notifications (optional):** the morning brief and end-of-month coach nudge
  can be pushed to your phone via [ntfy](https://ntfy.sh); they are private by
  default (a generic ping unless you opt in to including content).

## Security

The security model — single-user gatekeeper, secrets confined to `.env`, strict
CSP, tailnet-only deployment, and fail-fast configuration — is documented in
[SECURITY.md](SECURITY.md), which also explains how to report a vulnerability.

## License & contributing

- **License:** [LICENSE.md](LICENSE.md) — PolyForm Noncommercial 1.0.0
  (noncommercial use only; copyright © 2026 Kone Tshivhinda).
- **Contributors:** [CONTRIBUTORS.md](CONTRIBUTORS.md).

## Architecture

See `CLAUDE.md`, `backend/CLAUDE.md`, and `frontend/CLAUDE.md` for the full map,
invariants, and conventions.
