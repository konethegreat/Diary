"""What each AI feature sends to the active provider, and what it keeps.

These are the data flows described in docs/DATA_FLOWS.md: every assertion
looks at the request that actually left the app (recorded by FakeNetwork).
"""
from datetime import date, timedelta

import pytest
from helpers import run

from backend.config import settings
from backend.models import Brief, Entry, Reminder, Setting, Topic
from backend.services import ai
from backend.services import brief as brief_service

CLAUDE = "api.anthropic.com"
OLLAMA = "ollama.test"
EM_DASH = "—"


def stored(db, key):
    db.expire_all()
    row = db.get(Setting, key)
    return row.value if row else None


def topic_id(db, name):
    return db.query(Topic).filter(Topic.name == name).one().id


# ------------------------------------------------------------- polish ---


def test_polish_sends_the_raw_text_to_claude_for_polish_and_mood(client, db, net, anthropic_key, add_entry):
    net.anthropic_reply = lambda body: "4" if body["max_tokens"] == 4 else "**Polished** summary"
    entry = add_entry(title="Garden", text="messy raw words")

    response = client.post(f"/api/entries/{entry.id}/polish")

    assert response.status_code == 200
    assert "<strong>Polished</strong>" in response.text
    assert net.hosts() == [CLAUDE, CLAUDE, OLLAMA]
    polish_request, mood_request, embed_request = net.requests
    polish, mood = net.json_body(polish_request), net.json_body(mood_request)
    assert polish["system"] == ai.POLISH_SYSTEM
    assert polish["messages"] == [{"role": "user", "content": "messy raw words"}]
    assert polish["max_tokens"] == 1500
    assert mood["system"] == ai.MOOD_SYSTEM
    assert mood["messages"] == [{"role": "user", "content": "messy raw words"}]
    assert mood["max_tokens"] == 4
    # the embedding is refreshed from the polished text, locally
    assert net.json_body(embed_request)["prompt"] == "Garden\n**Polished** summary"
    db.refresh(entry)
    assert (entry.polished_text, entry.mood) == ("**Polished** summary", 4)


def test_polish_with_the_local_provider_never_contacts_claude(client, db, net, anthropic_key, add_entry):
    ai.set_provider(db, "local")
    net.ollama_reply = lambda body: (
        "5" if body["messages"][0]["content"] == ai.MOOD_SYSTEM else "Polished locally"
    )
    entry = add_entry(title="Garden", text="messy raw words")

    client.post(f"/api/entries/{entry.id}/polish")

    assert net.hosts() == [OLLAMA, OLLAMA, OLLAMA]
    assert [r.url.path for r in net.requests] == ["/api/chat", "/api/chat", "/api/embeddings"]
    db.refresh(entry)
    assert (entry.polished_text, entry.mood) == ("Polished locally", 5)


def test_polish_without_a_key_shows_the_error_and_leaves_the_entry_untouched(client, db, net, add_entry):
    entry = add_entry(text="raw words")

    response = client.post(f"/api/entries/{entry.id}/polish")

    assert response.status_code == 200
    assert "AI error: ANTHROPIC_API_KEY is not set" in response.text
    assert net.requests == []
    db.refresh(entry)
    assert (entry.polished_text, entry.mood) == ("", None)


def test_polishing_an_unknown_entry_is_a_404(client, net, anthropic_key):
    assert client.post("/api/entries/999/polish").status_code == 404
    assert net.requests == []


@pytest.mark.parametrize(
    "reply, expected",
    [("3 (neutral)", 3), (" 5\n", 5), ("banana", 2), ("9", 2), ("0", 2), ("", 2)],
)
def test_mood_scoring_is_best_effort_and_keeps_the_previous_score(
    client, db, net, anthropic_key, add_entry, reply, expected
):
    net.anthropic_reply = lambda body: reply if body["max_tokens"] == 4 else "Polished"
    entry = add_entry(text="raw words", mood=2)

    client.post(f"/api/entries/{entry.id}/polish")

    db.refresh(entry)
    assert entry.polished_text == "Polished"
    assert entry.mood == expected


# --------------------------------------------------------------- chat ---


def test_chat_context_holds_only_entries_similar_to_the_question(client, net, anthropic_key, add_entry):
    net.embed_rules = [("gardening", [1.0, 0.0, 0.0])]
    add_entry(title="Tomatoes", text="Planted tomatoes today", day=date(2026, 3, 5),
              topic="Personal", vector=[1.0, 1.0, 0.0])  # cosine 0.71
    add_entry(title="Taxes", text="Filed the tax return", day=date(2026, 3, 6),
              vector=[0.0, 1.0, 0.0])  # cosine 0.0
    add_entry(title="Almost", text="Barely related note", day=date(2026, 3, 7),
              vector=[0.25, 0.9682, 0.0])  # cosine 0.25: under the 0.3 cut-off

    response = client.post("/api/chat", data={"question": "How is my gardening going?"})

    assert net.hosts() == [OLLAMA, CLAUDE]
    question_embedding, answer_request = net.requests
    assert net.json_body(question_embedding)["prompt"] == "How is my gardening going?"
    body = net.json_body(answer_request)
    assert body["system"] == ai.CHAT_SYSTEM
    prompt = body["messages"][0]["content"]
    assert f"Entry 2026-03-05 [Personal] {EM_DASH} Tomatoes\nPlanted tomatoes today" in prompt
    assert "Question: How is my gardening going?" in prompt
    assert "Filed the tax return" not in prompt
    assert "Barely related note" not in prompt
    assert f"2026-03-05 {EM_DASH} Tomatoes" in response.text  # listed as a source
    assert "Taxes" not in response.text


def test_chat_uses_at_most_the_six_best_matches(client, net, anthropic_key, add_entry):
    net.embed_rules = [("a question", [1.0, 0.0, 0.0])]
    for i in range(8):  # all above the cut-off; higher i = less similar
        add_entry(title=f"Note {i}", text=f"body {i}", vector=[1.0, 0.1 * i, 0.0])

    client.post("/api/chat", data={"question": "a question"})

    prompt = net.json_body(net.to(CLAUDE)[0])["messages"][0]["content"]
    assert all(f"Note {i}" in prompt for i in range(6))
    assert "Note 6" not in prompt and "Note 7" not in prompt


def test_chat_with_nothing_relevant_sends_no_diary_text(client, net, anthropic_key, add_entry):
    net.embed_rules = [("weather", [1.0, 0.0, 0.0])]
    add_entry(title="Taxes", text="Filed the tax return", vector=[0.0, 1.0, 0.0])

    response = client.post("/api/chat", data={"question": "weather?"})

    prompt = net.json_body(net.to(CLAUDE)[0])["messages"][0]["content"]
    assert "(no relevant entries found)" in prompt
    assert "Filed the tax return" not in prompt
    assert "ANTHROPIC-REPLY" in response.text


def test_chat_while_ollama_is_down_sends_no_diary_text(client, net, anthropic_key, add_entry):
    add_entry(title="Garden", text="Planted tomatoes", vector=[1.0, 0.0, 0.0])
    net.ollama_up = False

    client.post("/api/chat", data={"question": "anything"})

    assert net.hosts() == [OLLAMA, CLAUDE]
    prompt = net.json_body(net.to(CLAUDE)[0])["messages"][0]["content"]
    assert "(no relevant entries found)" in prompt
    assert "Planted tomatoes" not in prompt


def test_chat_with_the_local_provider_stays_on_the_ollama_host(client, db, net, anthropic_key, add_entry):
    ai.set_provider(db, "local")
    net.embed_rules = [("question", [1.0, 0.0, 0.0])]
    add_entry(title="Garden", text="Planted tomatoes", vector=[1.0, 0.0, 0.0])

    client.post("/api/chat", data={"question": "a question"})

    assert [r.url.path for r in net.requests] == ["/api/embeddings", "/api/chat"]
    assert set(net.hosts()) == {OLLAMA}
    assert "Planted tomatoes" in net.json_body(net.requests[1])["messages"][1]["content"]


def test_chat_without_a_key_reports_the_error_in_the_thread(client, net):
    response = client.post("/api/chat", data={"question": "anything"})

    assert "AI error: ANTHROPIC_API_KEY is not set" in response.text
    assert net.hosts() == [OLLAMA]  # only the question was embedded


# ------------------------------------------------------- weekly review ---


def test_the_weekly_review_sends_the_last_seven_days_and_caches_the_result(
    client, db, net, anthropic_key, add_entry
):
    today = date.today()
    add_entry(title="Too old", text="eight days ago", day=today - timedelta(days=7))
    add_entry(title="Edge", text="six days ago", day=today - timedelta(days=6), mood=2)
    add_entry(title="Today", text="raw words", polished="Polished today", day=today, mood=5)
    add_entry(title="Tomorrow", text="not yet", day=today + timedelta(days=1))

    response = client.post("/api/review")

    assert "ANTHROPIC-REPLY" in response.text
    assert net.hosts() == [CLAUDE]
    body = net.json_body(net.requests[0])
    assert body["system"] == ai.REVIEW_SYSTEM
    assert body["max_tokens"] == 800
    assert body["messages"][0]["content"] == (
        f"[{(today - timedelta(days=6)).isoformat()}] Edge (mood 2/5)\nsix days ago\n\n"
        f"[{today.isoformat()}] Today (mood 5/5)\nPolished today"
    )
    iso = today.isocalendar()
    assert stored(db, f"review:{iso.year}-W{iso.week:02d}") == "ANTHROPIC-REPLY"

    net.requests.clear()  # the saved review is shown without asking again
    assert "ANTHROPIC-REPLY" in client.get("/review").text
    assert net.requests == []


def test_the_weekly_review_needs_entries_and_calls_nothing_without_them(client, net, anthropic_key, add_entry):
    add_entry(title="Old", day=date.today() - timedelta(days=30))

    response = client.post("/api/review")

    assert "No entries in the last 7 days" in response.text
    assert net.requests == []


def test_a_failed_review_is_reported_and_not_cached(client, db, net, anthropic_key, add_entry):
    add_entry(title="Today", text="words")
    net.fail = lambda request: True

    response = client.post("/api/review")

    assert "Internal Server Error" in response.text
    iso = date.today().isocalendar()
    assert stored(db, f"review:{iso.year}-W{iso.week:02d}") is None


# ------------------------------------------------------ topic summaries ---


def test_a_topic_summary_sends_that_topics_entries_for_the_period(client, db, net, anthropic_key, add_entry):
    add_entry(title="Ship", text="shipped v1", day=date(2026, 3, 4), topic="Work", mood=3)
    add_entry(title="Other month", text="april work", day=date(2026, 4, 2), topic="Work")
    add_entry(title="Not work", text="march personal", day=date(2026, 3, 5), topic="Personal")
    work = topic_id(db, "Work")

    response = client.post("/api/topics/summary", data={"topic_id": work, "scope": "2026-03"})

    assert "ANTHROPIC-REPLY" in response.text
    body = net.json_body(net.requests[0])
    assert body["system"] == ai.TOPIC_SUMMARY_SYSTEM
    assert body["messages"][0]["content"] == (
        "Topic: Work\nPeriod: March 2026\n\nEntries:\n\n[2026-03-04] Ship (mood 3/5)\nshipped v1"
    )
    assert stored(db, f"topic-summary:{work}:2026-03") == "ANTHROPIC-REPLY"


def test_a_topic_summary_covers_at_most_the_latest_200_entries_of_2500_characters(
    client, db, net, anthropic_key
):
    work = topic_id(db, "Work")
    db.add_all(
        Entry(title=f"n{i:03d}", raw_text="x" * 2600, entry_date=date(2026, 1, 1) + timedelta(days=i),
              topic_id=work)
        for i in range(205)
    )
    db.commit()

    client.post("/api/topics/summary", data={"topic_id": work, "scope": "all"})

    prompt = net.json_body(net.requests[0])["messages"][0]["content"]
    assert prompt.count("] n") == 200
    assert "] n004\n" not in prompt and "] n005\n" in prompt and "] n204\n" in prompt
    assert "x" * 2500 in prompt and "x" * 2501 not in prompt


def test_a_topic_summary_with_no_entries_calls_nothing(client, db, net, anthropic_key):
    response = client.post(
        "/api/topics/summary", data={"topic_id": topic_id(db, "Growth"), "scope": "all"}
    )

    assert "No Growth entries for all time" in response.text
    assert net.requests == []


# -------------------------------------------------------------- coach ---


def _coach_fixtures(db, add_entry):
    add_entry(title="Launch", text="shipped it", day=date(2026, 3, 3), topic="Work", mood=4)
    add_entry(title="Long", text="x" * 3000, day=date(2026, 3, 10))
    add_entry(title="Outside", text="february note", day=date(2026, 2, 28))
    db.add(Setting(key="coach:profile", value="Likes mountains"))
    db.add(Setting(key="coach:2026-02", value="February session text"))
    db.commit()


def test_a_coach_session_sends_the_month_and_updates_the_profile(client, db, net, anthropic_key, add_entry):
    _coach_fixtures(db, add_entry)
    net.anthropic_reply = lambda body: "SESSION" if body["max_tokens"] == 1200 else "NEW-PROFILE"

    response = client.post("/api/coach", data={"ym": "2026-03"})

    assert net.hosts() == [CLAUDE, CLAUDE]
    session, profile = (net.json_body(r) for r in net.requests)
    assert session["system"] == ai.COACH_SYSTEM
    prompt = session["messages"][0]["content"]
    assert prompt.startswith(
        "Your profile notes on them so far:\nLikes mountains\n\n"
        "Last month's session:\nFebruary session text\n\n"
        "Month: March 2026\nEmotional shape of the month:\n"
    )
    assert "Average 4.0/5." in prompt
    assert "[2026-03-03] Launch (topic: Work) (mood 4/5)\nshipped it" in prompt
    assert "x" * 2500 in prompt and "x" * 2501 not in prompt  # long entries are cut
    assert "february note" not in prompt
    assert profile["system"] == ai.COACH_PROFILE_SYSTEM
    assert profile["max_tokens"] == 500
    assert profile["messages"][0]["content"].startswith(
        "Existing notes:\nLikes mountains\n\nThis month's diary entries:\n\n[2026-03-03] Launch"
    )
    assert stored(db, "coach:2026-03") == "SESSION"
    assert stored(db, "coach:profile") == "NEW-PROFILE"
    assert "SESSION" in response.text and "NEW-PROFILE" in response.text


def test_the_session_is_kept_when_the_profile_update_fails(client, db, net, anthropic_key, add_entry):
    _coach_fixtures(db, add_entry)
    net.anthropic_reply = lambda body: "SESSION"
    net.fail = lambda request: net.json_body(request)["max_tokens"] == 500

    response = client.post("/api/coach", data={"ym": "2026-03"})

    assert response.status_code == 200 and "SESSION" in response.text
    assert stored(db, "coach:2026-03") == "SESSION"
    assert stored(db, "coach:profile") == "Likes mountains"


def test_a_failed_coach_session_saves_nothing_and_skips_the_profile_update(
    client, db, net, anthropic_key, add_entry
):
    _coach_fixtures(db, add_entry)
    net.fail = lambda request: True

    response = client.post("/api/coach", data={"ym": "2026-03"})

    assert "Internal Server Error" in response.text
    assert len(net.requests) == 1
    assert stored(db, "coach:2026-03") is None
    assert stored(db, "coach:profile") == "Likes mountains"


def test_the_coach_needs_entries_in_the_month(client, net, anthropic_key):
    response = client.post("/api/coach", data={"ym": "2026-03"})

    assert "No entries in March 2026" in response.text
    assert net.requests == []


# ---------------------------------------------------------- morning brief ---


def test_the_brief_prompt_holds_yesterdays_entries_and_open_reminders(client, db, net, anthropic_key, add_entry):
    today = date.today()
    yesterday = today - timedelta(days=1)
    add_entry(title="Yesterday", text="raw words", polished="Polished words", day=yesterday)
    add_entry(title="Earlier", text="two days ago", day=today - timedelta(days=2))
    db.add_all(
        [
            Reminder(text="Pay rent", due_date=today),
            Reminder(text="Overdue thing", due_date=yesterday),
            Reminder(text="Already done", due_date=today, done=True),
            Reminder(text="Later", due_date=today + timedelta(days=1)),
        ]
    )
    db.commit()

    response = client.get("/api/brief")

    assert "ANTHROPIC-REPLY" in response.text
    assert net.hosts() == ["date.nager.at", CLAUDE]  # holidays by year + country only
    assert net.requests[0].url.path == f"/api/v3/PublicHolidays/{today.year}/ZA"
    body = net.json_body(net.requests[1])
    assert body["system"] == brief_service.BRIEF_SYSTEM
    assert body["max_tokens"] == 600
    prompt = body["messages"][0]["content"]
    assert f"Today is {today.strftime('%A, %B %d, %Y')}." in prompt
    assert f"- Pay rent (due {today})" in prompt
    assert f"- Overdue thing (due {yesterday})" in prompt
    assert "Already done" not in prompt and "Later" not in prompt
    assert "Yesterday\nPolished words" in prompt
    assert "two days ago" not in prompt and "raw words" not in prompt
    assert "Weather:" not in prompt


def test_the_brief_is_cached_per_day_until_it_is_refreshed(client, db, net, anthropic_key):
    replies = iter(["first brief", "second brief"])
    net.anthropic_reply = lambda body: next(replies)

    assert "first brief" in client.get("/api/brief").text
    asked = len(net.to(CLAUDE))
    assert "first brief" in client.get("/api/brief").text
    assert len(net.to(CLAUDE)) == asked  # served from the cache

    assert "second brief" in client.get("/api/brief?force=true").text
    db.expire_all()
    assert db.get(Brief, date.today()).content == "second brief"


def test_weather_is_only_requested_when_coordinates_are_configured(client, net, anthropic_key, monkeypatch):
    client.get("/api/brief")
    assert "api.open-meteo.com" not in net.hosts()

    monkeypatch.setattr(settings, "LATITUDE", "-26.20")
    monkeypatch.setattr(settings, "LONGITUDE", "28.04")
    client.get("/api/brief?force=true")

    (weather,) = net.to("api.open-meteo.com")
    assert dict(weather.url.params) == {
        "latitude": "-26.20",
        "longitude": "28.04",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "timezone": "auto",
        "forecast_days": "1",
    }
    prompt = net.json_body(net.to(CLAUDE)[-1])["messages"][0]["content"]
    assert "Weather: Clear, 10–21°C." in prompt


def test_a_public_holiday_is_mentioned_in_the_brief(client, net, anthropic_key):
    net.holidays = [{"date": date.today().isoformat(), "localName": "Test Day"}]

    client.get("/api/brief")

    prompt = net.json_body(net.to(CLAUDE)[0])["messages"][0]["content"]
    assert "Today is a public holiday: Test Day." in prompt


def test_the_brief_error_is_shown_instead_of_a_brief(client, net):
    response = client.get("/api/brief")

    assert "generate the brief" in response.text
    assert "ANTHROPIC_API_KEY is not set" in response.text
