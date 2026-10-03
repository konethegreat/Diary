"""Shared fixtures: a hermetic copy of the app.

* ``backend.config`` reads the environment at import time and refuses to start
  without ``ALLOWED_EMAIL`` / ``SECRET_KEY``, so everything is configured here,
  *before* ``backend`` is imported anywhere. Variables that are set (even to
  an empty string) are never overridden by a developer's real ``.env``.
* The database is a throw-away SQLite file in the system temp directory; the
  real ``data/`` folder is never touched.
* Every outbound HTTP request the app makes is answered by ``FakeNetwork`` and
  recorded, so tests can assert exactly what is sent where. A request to a
  host the fake does not know about fails the test.
"""
import atexit
import json
import os
import secrets
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import OWNER, TEST_API_KEY

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="diary-tests-"))
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)

os.environ.update(
    {
        "ALLOWED_EMAIL": OWNER,
        "SECRET_KEY": secrets.token_hex(32),
        "AUTH_MODE": "dev",
        "TRUST_TAILNET": "",
        "DATABASE_PATH": str(_TMP / "diary-test.db"),
        # Everything below could otherwise reach a real service or pick up a
        # developer's own configuration from .env.
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": "test-anthropic-model",
        "OLLAMA_BASE_URL": "http://ollama.test:11434",
        "OLLAMA_MODEL": "test-chat-model",
        "OLLAMA_EMBED_MODEL": "test-embed-model",
        "NTFY_TOPIC": "",
        "NTFY_SERVER": "https://ntfy.test",
        "NTFY_SEND_CONTENT": "",
        "APP_URL": "",
        "LATITUDE": "",
        "LONGITUDE": "",
        "COUNTRY_CODE": "ZA",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "BRIEF_HOUR": "6",
    }
)

from backend.config import settings  # noqa: E402  (must follow the env setup)


class FakeNetwork:
    """Answers and records every outbound HTTP request made through httpx."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.unexpected: list[str] = []
        self.ollama_up = True
        self.holidays: list[dict] = []
        # (keyword in the embedded text, vector); first match wins.
        self.embed_rules: list[tuple[str, list[float]]] = []
        self.default_vector = [0.0, 0.0, 1.0]

    # -- scripted replies (tests may override these) --------------------
    def anthropic_reply(self, body: dict) -> str:
        return "4" if body.get("max_tokens") == 4 else "ANTHROPIC-REPLY"

    def ollama_reply(self, body: dict) -> str:
        return "OLLAMA-REPLY"

    def embed(self, text: str) -> list[float]:
        for keyword, vector in self.embed_rules:
            if keyword in text:
                return vector
        return self.default_vector

    # -- helpers for assertions -----------------------------------------
    def to(self, host: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host]

    def hosts(self) -> list[str]:
        return [r.url.host for r in self.requests]

    @staticmethod
    def json_body(request: httpx.Request) -> dict:
        return json.loads(request.content)

    # -- the transport handler ------------------------------------------
    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        if host == "api.anthropic.com" and path == "/v1/messages":
            body = self.json_body(request)
            return httpx.Response(
                200, json={"content": [{"type": "text", "text": self.anthropic_reply(body)}]}
            )
        if host == "ollama.test":
            if not self.ollama_up:
                raise httpx.ConnectError("connection refused", request=request)
            body = self.json_body(request)
            if path == "/api/chat":
                return httpx.Response(
                    200, json={"message": {"role": "assistant", "content": self.ollama_reply(body)}}
                )
            if path == "/api/embeddings":
                return httpx.Response(200, json={"embedding": self.embed(body["prompt"])})
        if host == "api.open-meteo.com":
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "weather_code": [0],
                        "temperature_2m_max": [21.4],
                        "temperature_2m_min": [9.6],
                    }
                },
            )
        if host == "date.nager.at":
            return httpx.Response(200, json=self.holidays)
        if host == "zenquotes.io":
            return httpx.Response(200, json=[{"q": "A test quote.", "a": "Tester"}])
        if host == "ntfy.test":
            return httpx.Response(200, text="ok")
        self.unexpected.append(str(request.url))
        return httpx.Response(599)


@pytest.fixture(autouse=True)
def net(monkeypatch):
    """Route every httpx.AsyncClient to FakeNetwork; fail on unknown hosts."""
    from backend.services import external

    fake = FakeNetwork()
    real_client = httpx.AsyncClient

    class _Client(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(fake.handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    external._cache.clear()
    yield fake
    external._cache.clear()
    assert not fake.unexpected, f"unexpected outbound requests: {fake.unexpected}"


@pytest.fixture(autouse=True)
def fresh_db():
    """Empty database with the preset topics before every test."""
    from backend import models  # noqa: F401  (registers the tables)
    from backend.database import Base, engine, init_db

    Base.metadata.drop_all(engine)
    init_db()


@pytest.fixture
def db():
    from backend.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def anthropic_key(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", TEST_API_KEY)
    return TEST_API_KEY


@pytest.fixture
def client():
    """The owner on the loopback interface (AUTH_MODE=dev signs them in)."""
    from backend.main import app

    return TestClient(app)


@pytest.fixture
def remote_client():
    """A client on a public address, without a session. Redirects not followed."""
    from backend.main import app

    return TestClient(app, client=("203.0.113.7", 50000), follow_redirects=False)


@pytest.fixture
def add_entry(db):
    """Factory: insert an entry directly (optionally with an embedding)."""
    from backend.models import Entry, Topic
    from backend.services import embeddings

    def _add(title="Entry", text="body", day=None, topic=None, mood=None, polished="", vector=None):
        topic_id = None
        if topic:
            topic_id = db.query(Topic).filter(Topic.name == topic).one().id
        entry = Entry(
            title=title,
            raw_text=text,
            polished_text=polished,
            entry_date=day or date.today(),
            topic_id=topic_id,
            mood=mood,
            embedding=embeddings.pack(vector) if vector else None,
        )
        db.add(entry)
        db.commit()
        return entry

    return _add
