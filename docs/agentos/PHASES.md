# Phases

Ordered work for Diary, derived from the repository state on 2026-11-20
(HEAD 89fc294, 12 test modules under `tests/`, no open issues, CI runs
`pytest -q` on every pull request).

Each phase is a unit of intent. The tasks that implement it live in
TASKS.md under the same heading, ordered, each small enough for one pull
request.

## Phase 1: Document the system that exists

The repository has no `docs/` directory at all. A new contributor (human or
agent) must reverse engineer the request flow from `backend/main.py`,
`backend/routers/`, and `backend/services/` before touching anything. Write
down what is there before changing it.

Done when: `docs/ARCHITECTURE.md` describes the routers, services, database
schema, templating model, and the two AI providers (Claude API and local
Ollama) with the file that owns each, and `docs/CONFIGURATION.md` lists every
environment variable that `backend/config.py` validates.

## Phase 2: Close the test gaps in the AI and calendar surfaces

`tests/` covers entries, pages, export, notifications, similarity search, the
gatekeeper, and provider selection. The brief, coach, review, and calendar
routers have no dedicated test module, and the failure path when a provider
returns malformed output is only partially exercised.

Done when: each router in `backend/routers/` has a matching test module
(`test_brief.py`, `test_coach.py`, `test_review.py`, `test_calendar.py`) that
covers the success path, the empty-data path, and a provider failure, and the
suite stays green with no live network calls.

## Phase 3: Dependency and data safety

`requirements.txt` and `requirements-dev.txt` are installed unpinned into a
fresh virtual environment, so two installs a month apart can resolve
differently. The SQLite database in `data/` is the only copy of the owner's
entries and has no documented backup or upgrade procedure beyond the schema
upgrade already tested in `test_entries_and_pages.py`.

Done when: CI resolves a locked dependency set (pinned versions committed),
`docs/BACKUP.md` documents how to snapshot and restore the SQLite file, and a
test exercises the schema upgrade from the previous version against a
fixture database.

## Phase 4: Packaging and install runbook

The app is a PWA meant to be installed on the owner's machine. The README
explains the first run, but nothing documents the recurring operations: how
to switch between Claude and Ollama, how to rotate `SECRET_KEY` without
logging everyone out permanently, and how to run the app as a background
service on Windows.

Done when: `docs/OPERATIONS.md` covers provider switching, key rotation,
and restart, and the README links to it from the quick start section.

## Phase 5: Maintenance loop

With documentation, tests, and the runbook in place, the remaining work is
keeping them true: a small pull request whenever a router, service, or
environment variable changes.

Done when: every merged pull request that changes a router, service, or
environment variable updates the matching documentation file in the same
pull request, and `docs/agentos/REPORT.md` carries one line per merged
pull request.
