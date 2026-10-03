"""End to end: where can a diary entry travel? (docs/DATA_FLOWS.md)

Every optional integration is switched on, every feature is used once with an
entry that contains a unique marker, and the recorded requests show which
hosts received the marker and the API key.
"""
from datetime import date

import pytest
from helpers import TEST_API_KEY, run

from backend import main
from backend.config import settings
from backend.models import Entry, Topic
from backend.services import ai

MARKER = "zx-private-marker-81"
CLAUDE = "api.anthropic.com"
OLLAMA = "ollama.test"
EVERY_HOST = {CLAUDE, OLLAMA, "api.open-meteo.com", "date.nager.at", "zenquotes.io", "ntfy.test"}


@pytest.fixture
def fully_configured(monkeypatch):
    """Claude key, ntfy topic and weather coordinates all set."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", TEST_API_KEY)
    monkeypatch.setattr(settings, "NTFY_TOPIC", "private-test-topic")
    monkeypatch.setattr(settings, "APP_URL", "https://diary.example.ts.net")
    monkeypatch.setattr(settings, "LATITUDE", "-26.20")
    monkeypatch.setattr(settings, "LONGITUDE", "28.04")


def use_every_feature(client, db):
    today = date.today()
    work = db.query(Topic).filter(Topic.name == "Work").one().id
    saved = client.post(
        "/api/entries",
        data={
            "title": f"Title {MARKER}",
            "raw_text": f"Body {MARKER}",
            "entry_date": today.isoformat(),
            "topic_id": str(work),
        },
    )
    assert saved.status_code == 200
    entry_id = db.query(Entry).one().id

    client.post(f"/api/entries/{entry_id}/polish")
    client.post("/api/chat", data={"question": f"What did I write about {MARKER}?"})
    client.post("/api/review")
    client.post("/api/coach", data={"ym": today.strftime("%Y-%m")})
    client.post("/api/topics/summary", data={"topic_id": str(work), "scope": "all"})
    client.get("/api/brief?force=true")
    for path in ("/", "/calendar", "/export/all.pdf"):
        assert client.get(path).status_code == 200
    run(main._scheduled_brief())


def carriers(net):
    """Hosts that received the marker in a URL, header or body."""
    return {
        request.url.host
        for request in net.requests
        if MARKER in str(request.url) + str(request.headers) + request.content.decode("utf-8", "replace")
    }


def test_with_the_claude_provider_diary_text_reaches_only_claude_and_ollama(client, db, net, fully_configured):
    use_every_feature(client, db)

    assert carriers(net) == {CLAUDE, OLLAMA}


def test_with_the_local_provider_diary_text_never_leaves_the_ollama_host(client, db, net, fully_configured):
    ai.set_provider(db, "local")

    use_every_feature(client, db)

    assert carriers(net) == {OLLAMA}
    assert CLAUDE not in net.hosts()


def test_the_api_key_goes_only_to_anthropic_and_only_as_a_header(client, db, net, fully_configured):
    use_every_feature(client, db)

    assert net.to(CLAUDE)  # the scenario really used Claude
    for request in net.requests:
        body = request.content.decode("utf-8", "replace")
        if request.url.host == CLAUDE:
            assert request.headers["x-api-key"] == TEST_API_KEY
            assert TEST_API_KEY not in str(request.url) + body
        else:
            assert TEST_API_KEY not in str(request.url) + str(request.headers) + body


def test_the_complete_list_of_destinations_is_the_documented_one(client, db, net, fully_configured):
    use_every_feature(client, db)

    assert set(net.hosts()) == EVERY_HOST


def test_viewing_pages_sends_no_diary_content(client, net, add_entry):
    add_entry(title=MARKER, text=MARKER)

    for path in ("/", "/calendar", "/review", "/coach", "/topics", "/chat"):
        assert client.get(path).status_code == 200

    assert set(net.hosts()) <= {"date.nager.at", "zenquotes.io"}
    assert carriers(net) == set()
