"""Entries, reminders, topics, schema upgrades and the pages that show them."""
import re
from datetime import date

from sqlalchemy import create_engine, inspect, text

from backend import database
from backend.config import settings
from backend.database import PRESET_TOPICS, init_db
from backend.models import Entry, Reminder, Topic


# ------------------------------------------------------------- entries ---


def test_a_saved_entry_appears_on_its_own_day_only(client):
    client.post(
        "/api/entries",
        data={"title": "Standup", "raw_text": "Discussed the roadmap", "entry_date": "2026-03-05"},
    )

    assert "Discussed the roadmap" in client.get("/?d=2026-03-05").text
    assert "Discussed the roadmap" not in client.get("/?d=2026-03-06").text


def test_an_entry_can_be_filed_under_a_topic(client, db):
    work = db.query(Topic).filter(Topic.name == "Work").one()

    response = client.post(
        "/api/entries",
        data={"title": "T", "raw_text": "x", "entry_date": "2026-03-05", "topic_id": str(work.id)},
    )

    assert '<span class="topic-pill">Work</span>' in response.text
    assert db.query(Entry).one().topic_id == work.id


def test_deleting_an_entry_removes_it_and_a_second_delete_is_harmless(client, db, add_entry):
    entry = add_entry(title="Gone")

    assert client.delete(f"/api/entries/{entry.id}").status_code == 200
    assert db.query(Entry).count() == 0
    assert client.delete(f"/api/entries/{entry.id}").status_code == 200


def test_an_entry_needs_text(client, db):
    response = client.post("/api/entries", data={"title": "No body", "entry_date": "2026-03-05"})

    assert response.status_code == 422
    assert db.query(Entry).count() == 0


# ----------------------------------------------------------- reminders ---


def test_reminders_can_be_added_toggled_and_deleted(client, db):
    added = client.post(
        "/api/reminders", data={"text": "  Call the bank  ", "due_date": date.today().isoformat()}
    )
    assert "Call the bank" in added.text
    reminder = db.query(Reminder).one()
    assert (reminder.text, reminder.done) == ("Call the bank", False)

    client.post(f"/api/reminders/{reminder.id}/toggle")
    db.refresh(reminder)
    assert reminder.done is True
    client.post(f"/api/reminders/{reminder.id}/toggle")
    db.refresh(reminder)
    assert reminder.done is False

    client.delete(f"/api/reminders/{reminder.id}")
    assert db.query(Reminder).count() == 0


def test_the_reminder_list_carries_overdue_items_forward_and_sorts_done_ones_last(client, db):
    day = date(2026, 3, 10)
    db.add_all(
        [
            Reminder(text="Overdue", due_date=date(2026, 3, 1)),
            Reminder(text="Today done", due_date=day, done=True),
            Reminder(text="Today open", due_date=day),
            Reminder(text="Future", due_date=date(2026, 3, 11)),
        ]
    )
    db.commit()

    html = client.get("/api/reminders?d=2026-03-10").text

    assert "Future" not in html
    assert html.index("Overdue") < html.index("Today open") < html.index("Today done")


def test_changing_a_reminder_that_does_not_exist_is_harmless(client):
    assert client.post("/api/reminders/999/toggle").status_code == 200
    assert client.delete("/api/reminders/999").status_code == 200


# -------------------------------------------------------------- topics ---


def test_the_preset_topics_are_seeded_once(db):
    assert {topic.name for topic in db.query(Topic)} == {name for name, _ in PRESET_TOPICS}

    init_db()  # starting the app again must not duplicate them

    assert db.query(Topic).count() == len(PRESET_TOPICS)


def test_custom_topics_are_trimmed_not_duplicated_and_blank_names_are_ignored(client, db):
    client.post("/api/topics", data={"name": "  Side projects  "})
    client.post("/api/topics", data={"name": "Side projects"})
    client.post("/api/topics", data={"name": "   "})

    names = [topic.name for topic in db.query(Topic)]
    assert names.count("Side projects") == 1
    assert len(names) == len(PRESET_TOPICS) + 1


# ------------------------------------------------------------ database ---


def test_the_mood_column_is_added_to_an_older_database(tmp_path, monkeypatch):
    old = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with old.begin() as connection:
        connection.execute(text("CREATE TABLE entries (id INTEGER PRIMARY KEY, title VARCHAR(200))"))
    monkeypatch.setattr(database, "engine", old)

    database._migrate()
    database._migrate()  # running it twice is harmless

    assert "mood" in {column["name"] for column in inspect(old).get_columns("entries")}


# --------------------------------------------------------------- pages ---


def _calendar_cell(html: str, day: str) -> str:
    match = re.search(rf'<a class="cal-cell[^"]*" href="/\?d={day}">(.*?)</a>', html, re.S)
    assert match, f"no calendar cell for {day}"
    return match.group(1)


def test_the_calendar_marks_entries_reminders_holidays_and_moods(client, db, net, add_entry):
    net.holidays = [{"date": "2026-03-21", "localName": "Human Rights Day"}]
    add_entry(title="A", day=date(2026, 3, 5), mood=5)
    db.add(Reminder(text="Renew licence", due_date=date(2026, 3, 9)))
    db.commit()

    html = client.get("/calendar?y=2026&m=3").text

    cell = _calendar_cell(html, "2026-03-05")
    assert "cal-dot" in cell and "\U0001f604" in cell  # one entry dot and the mood-5 face
    assert "cal-dot rem" in _calendar_cell(html, "2026-03-09")
    assert "Human Rights Day" in _calendar_cell(html, "2026-03-21")
    quiet = _calendar_cell(html, "2026-03-12")
    assert "cal-dot" not in quiet and "hol" not in quiet


def test_calendar_navigation_wraps_the_year(client):
    assert "/calendar?y=2025&m=12" in client.get("/calendar?y=2026&m=1").text
    assert "/calendar?y=2027&m=1" in client.get("/calendar?y=2026&m=12").text


def test_today_shows_weather_holiday_and_quote_while_other_days_do_not(client, net, monkeypatch):
    monkeypatch.setattr(settings, "LATITUDE", "-26.20")
    monkeypatch.setattr(settings, "LONGITUDE", "28.04")
    net.holidays = [{"date": date.today().isoformat(), "localName": "Test Day"}]

    today = client.get("/").text
    assert "Clear" in today and "Test Day" in today and "A test quote." in today

    past = client.get("/?d=2026-03-05").text
    assert "A test quote." not in past and "Clear" not in past


def test_memories_from_earlier_years_are_shown_on_the_day(client, add_entry):
    add_entry(title="A year ago", text="Planted tomatoes", day=date(2025, 3, 5))

    html = client.get("/?d=2026-03-05").text

    assert "On this day" in html and "A year ago" in html


def test_every_page_renders_on_an_empty_database(client):
    for path in ("/", "/calendar", "/review", "/coach", "/topics", "/chat", "/api/reminders"):
        assert client.get(path).status_code == 200, path
