"""Which AI service answers, what it is sent, and where the API key goes."""
import httpx
import pytest
from helpers import TEST_API_KEY, run

from backend.models import Entry
from backend.services import ai, embeddings

OLLAMA = "ollama.test"
CLAUDE = "api.anthropic.com"


def test_a_fresh_database_defaults_to_the_claude_api(db):
    assert ai.get_provider(db) == "anthropic"


def test_the_provider_choice_is_persisted_and_validated(db):
    assert ai.set_provider(db, "local") == "local"
    assert ai.get_provider(db) == "local"

    with pytest.raises(ValueError):
        ai.set_provider(db, "openai")
    assert ai.get_provider(db) == "local"


def test_the_toggle_endpoint_flips_between_the_two_providers(client, db):
    assert "Local (Ollama)" in client.post("/api/provider").text
    assert ai.get_provider(db) == "local"

    assert "Claude API" in client.post("/api/provider").text
    assert ai.get_provider(db) == "anthropic"


def test_claude_requests_carry_the_key_only_as_a_header(db, net, anthropic_key):
    reply = run(ai.complete(db, "SYSTEM-TEXT", "USER-TEXT", max_tokens=321))

    assert reply == "ANTHROPIC-REPLY"
    (request,) = net.requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == TEST_API_KEY
    assert request.headers["anthropic-version"] == "2023-06-01"
    assert net.json_body(request) == {
        "model": "test-anthropic-model",
        "max_tokens": 321,
        "system": "SYSTEM-TEXT",
        "messages": [{"role": "user", "content": "USER-TEXT"}],
    }
    assert TEST_API_KEY not in request.content.decode()


def test_claude_provider_without_a_key_fails_before_anything_is_sent(db, net):
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        run(ai.complete(db, "system", "diary text"))
    assert net.requests == []


def test_local_provider_talks_only_to_ollama_even_with_a_key_configured(db, net, anthropic_key):
    ai.set_provider(db, "local")

    reply = run(ai.complete(db, "SYSTEM-TEXT", "USER-TEXT"))

    assert reply == "OLLAMA-REPLY"
    (request,) = net.requests
    assert str(request.url) == "http://ollama.test:11434/api/chat"
    assert "x-api-key" not in request.headers
    assert net.json_body(request) == {
        "model": "test-chat-model",
        "stream": False,
        "messages": [
            {"role": "system", "content": "SYSTEM-TEXT"},
            {"role": "user", "content": "USER-TEXT"},
        ],
    }
    assert TEST_API_KEY not in request.content.decode()


@pytest.mark.parametrize("provider", ["anthropic", "local"])
def test_provider_http_errors_reach_the_caller(db, net, anthropic_key, provider):
    ai.set_provider(db, provider)
    net.fail = lambda request: True

    with pytest.raises(httpx.HTTPStatusError):
        run(ai.complete(db, "system", "prompt"))


def test_saving_an_entry_embeds_it_with_ollama_whatever_the_chat_provider(
    client, db, net, anthropic_key
):
    assert ai.get_provider(db) == "anthropic"

    response = client.post(
        "/api/entries",
        data={"title": "Garden", "raw_text": "Planted tomatoes", "entry_date": "2026-03-05"},
    )

    assert response.status_code == 200
    assert net.hosts() == [OLLAMA]  # nothing was sent to the Claude API
    (request,) = net.requests
    assert request.url.path == "/api/embeddings"
    assert net.json_body(request) == {
        "model": "test-embed-model",
        "prompt": "Garden\nPlanted tomatoes",
    }
    entry = db.query(Entry).one()
    assert entry.embedding_model == "test-embed-model"
    assert embeddings.unpack(entry.embedding) == [0.0, 0.0, 1.0]


def test_an_entry_is_still_saved_when_ollama_is_down(client, db, net):
    net.ollama_up = False

    response = client.post(
        "/api/entries",
        data={"title": "", "raw_text": "  Offline note  ", "entry_date": "2026-03-05"},
    )

    assert response.status_code == 200
    entry = db.query(Entry).one()
    assert (entry.title, entry.raw_text) == ("Untitled", "Offline note")
    assert entry.embedding is None
    assert net.hosts() == [OLLAMA]  # one failed attempt, nothing else
