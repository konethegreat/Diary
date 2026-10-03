"""Phone notifications (ntfy): opt-in, generic by default, never fatal."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from helpers import run

from backend import main
from backend.config import settings
from backend.models import Brief
from backend.services import notify

TOPIC = "private-test-topic"
NTFY = "ntfy.test"


@pytest.fixture
def ntfy(monkeypatch):
    """The owner has configured a ntfy topic."""
    monkeypatch.setattr(settings, "NTFY_TOPIC", TOPIC)


def freeze_today(monkeypatch, day):
    class FrozenDate(date):
        @classmethod
        def today(cls):
            return day

    monkeypatch.setattr(main, "date", FrozenDate)


# ---------------------------------------------------------------- push ---


def test_push_is_a_silent_no_op_without_a_topic(net):
    assert run(notify.push("Title", "Message")) is False
    assert net.requests == []


def test_push_posts_the_plain_text_message_to_the_topic(net, ntfy, monkeypatch):
    monkeypatch.setattr(settings, "APP_URL", "https://diary.example.ts.net/")

    sent = run(
        notify.push("Brief ☀", "**Bold** `code` text", click_path="/coach", priority="high", tags="brain")
    )

    assert sent is True
    (request,) = net.requests
    assert str(request.url) == f"https://ntfy.test/{TOPIC}"
    assert request.content == b"Bold code text"
    assert request.headers["Title"] == "Brief"  # header values stay ASCII
    assert request.headers["Priority"] == "high"
    assert request.headers["Tags"] == "brain"
    assert request.headers["Click"] == "https://diary.example.ts.net/coach"


def test_push_without_an_app_url_or_tags_sends_neither_header(net, ntfy):
    run(notify.push("Title", "Message"))

    (request,) = net.requests
    assert "Click" not in request.headers and "Tags" not in request.headers
    assert request.headers["Priority"] == "default"


def test_a_failing_ntfy_server_never_raises(net, ntfy):
    net.fail = lambda request: True

    assert run(notify.push("Title", "Message")) is False


def test_message_text_is_stripped_of_markdown_and_capped_at_300_characters():
    assert notify._plain("# Heading\n\n\n*item*") == "Heading\nitem"
    assert notify._plain("a" * 400) == "a" * 300 + "…"
    assert notify._plain("a" * 300) == "a" * 300


# ------------------------------------------------------- morning brief ---


def test_the_scheduled_brief_pings_without_diary_content_by_default(db, net, ntfy, anthropic_key):
    net.anthropic_reply = lambda body: "Focus on **MARKER-TEXT** today"

    run(main._scheduled_brief())

    (ping,) = net.to(NTFY)
    assert ping.content == b"Your morning brief is ready - tap to read it."
    assert ping.headers["Title"] == "Morning brief"
    db.expire_all()
    assert db.get(Brief, date.today()).content == "Focus on **MARKER-TEXT** today"


def test_the_brief_text_is_pushed_only_when_content_is_enabled(net, ntfy, anthropic_key, monkeypatch):
    monkeypatch.setattr(settings, "NTFY_SEND_CONTENT", True)
    net.anthropic_reply = lambda body: "Focus on **MARKER-TEXT** today"

    run(main._scheduled_brief())

    (ping,) = net.to(NTFY)
    assert ping.content == b"Focus on MARKER-TEXT today"


def test_without_a_topic_the_brief_is_made_but_nothing_is_pushed(db, net, anthropic_key):
    run(main._scheduled_brief())

    assert net.to(NTFY) == []
    db.expire_all()
    assert db.get(Brief, date.today()) is not None


def test_a_provider_failure_in_the_scheduled_brief_is_swallowed(db, net, ntfy):
    run(main._scheduled_brief())  # no API key: generating the brief fails

    assert net.to(NTFY) == []
    assert db.get(Brief, date.today()) is None


# --------------------------------------------------------- coach nudge ---


@pytest.mark.parametrize(
    "today, fires",
    [
        (date(2026, 1, 31), True),
        (date(2026, 2, 28), True),
        (date(2028, 2, 29), True),  # leap year
        (date(2026, 12, 31), True),
        (date(2026, 1, 30), False),
        (date(2028, 2, 28), False),  # the 29th follows
        (date(2026, 3, 15), False),
    ],
)
def test_the_coach_nudge_fires_only_on_the_last_day_of_the_month(net, ntfy, monkeypatch, today, fires):
    freeze_today(monkeypatch, today)

    run(main._coach_nudge())

    assert bool(net.to(NTFY)) is fires


def test_the_coach_nudge_carries_no_diary_content(net, ntfy, monkeypatch):
    freeze_today(monkeypatch, date(2026, 1, 31))

    run(main._coach_nudge())

    assert net.hosts() == [NTFY]
    (ping,) = net.requests
    assert ping.headers["Title"] == "January is wrapping up"
    assert ping.content == b"Your coach has read the whole month and is ready when you are."
    assert ping.headers["Tags"] == "brain"


# ----------------------------------------------------------- scheduler ---


def test_startup_schedules_the_brief_and_the_month_end_nudge(monkeypatch):
    jobs, events = [], []

    class RecordingScheduler:
        def add_job(self, func, trigger):
            jobs.append((func, {field.name: str(field) for field in trigger.fields}))

        def start(self):
            events.append("start")

        def shutdown(self, wait=True):
            events.append("shutdown")

    monkeypatch.setattr(main, "AsyncIOScheduler", RecordingScheduler)

    with TestClient(main.app):
        assert events == ["start"]

    assert events == ["start", "shutdown"]
    assert [(func, t["hour"], t["minute"]) for func, t in jobs] == [
        (main._scheduled_brief, str(settings.BRIEF_HOUR), "0"),
        (main._coach_nudge, "18", "0"),
    ]
