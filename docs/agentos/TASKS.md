# Tasks

Ordered tasks for Diary, one small reviewed pull request each. Headings
match PHASES.md. Work top to bottom; do not start a phase before the one
above it is done.

## Phase 1: Document the system that exists

- [ ] Research: map `backend/main.py`, every router in `backend/routers/`, and every service in `backend/services/`, and note for each: purpose, endpoints or entry points, and the tables it touches.
- [ ] Write `docs/ARCHITECTURE.md` with the request flow (HTMX request to router to service to SQLite and back through a Jinja template), the router and service inventory, and the database schema as defined in `backend/database.py`.
- [ ] Write `docs/CONFIGURATION.md` listing every environment variable validated by `backend/config.py`, what it is for, and whether it is required, with no values and no secrets.
- [ ] Review: link both documents from README.md and confirm no secret, `.env` content, em dash, or en dash appears in the added text.
- [ ] Improvement: add a short "where to start" paragraph to `docs/ARCHITECTURE.md` naming the three files a new contributor should read first.

## Phase 2: Close the test gaps in the AI and calendar surfaces

- [ ] Experiment: run the suite with coverage (`pytest --cov=backend`) once and record which modules in `backend/routers/` and `backend/services/` fall below 60 percent.
- [ ] Add `tests/test_brief.py` covering the morning brief success path with a stubbed AI service, the empty-data path, and a provider failure.
- [ ] Add `tests/test_coach.py` covering the monthly coach success path, the month with no entries, and a provider failure.
- [ ] Add `tests/test_review.py` covering the weekly review success path, the week with no entries, and the mood chart data shape.
- [ ] Add `tests/test_calendar.py` covering the month view, reminders on a day, and the holiday stub returning nothing.
- [ ] Improvement: factor the repeated stubbed-provider setup into `tests/helpers.py` so the new modules use one fixture instead of four copies.

## Phase 3: Dependency and data safety

- [ ] Research: diff the resolved versions from a fresh `pip install -r requirements-dev.txt` against the versions currently documented, and list every unpinned dependency.
- [ ] Pin every dependency in `requirements.txt` and `requirements-dev.txt` to the versions CI resolves, and confirm `pytest -q` stays green.
- [ ] Add a CI step that fails when an install resolves a version different from the lock, so drift is caught before it reaches the owner's machine.
- [ ] Write `docs/BACKUP.md` with the snapshot, restore, and verify commands for the SQLite file in `data/`, and a warning that the file is the only copy of the entries.
- [ ] Add a test that opens a fixture database at the previous schema version and asserts the upgrade in `backend/database.py` brings it to the current schema without losing rows.
- [ ] Review: run the full suite once and confirm the new test module and the pinned install both pass with no live network calls.

## Phase 4: Packaging and install runbook

- [ ] Write `docs/OPERATIONS.md` covering how the provider toggle between Claude and local Ollama works, where it is stored, and what happens when the chosen provider is unreachable.
- [ ] Document `SECRET_KEY` rotation in `docs/OPERATIONS.md`: how to generate a new value, what sessions it invalidates, and how the single-user gate re-establishes access.
- [ ] Document running the app as a background service on Windows (the command, the log location, and how to stop it) without inventing a service manager the repository does not use.
- [ ] Review: link `docs/OPERATIONS.md` from the README quick start and confirm the README and the document agree on every command.
- [ ] Improvement: add a troubleshooting section to `docs/OPERATIONS.md` for the three failures seen in this repository's history: a missing environment variable at startup, an unreachable Ollama, and a database locked by a second instance.

## Phase 5: Maintenance loop

- [ ] Update `CONTRIBUTORS.md` or the README with the rule that a pull request changing a router, service, or environment variable must update the matching document in the same pull request.
- [ ] Review: audit the repository for documentation that no longer matches the code, and open one small pull request per mismatch found.
- [ ] Improvement: append one line per merged pull request to `docs/agentos/REPORT.md` (date, pull request number, one sentence), and confirm the habit holds for two review cycles.
