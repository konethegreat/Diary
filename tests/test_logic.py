"""Pure logic: similarity search, mood statistics and date helpers."""
from datetime import date, timedelta

import pytest
from helpers import run

from backend.models import Entry
from backend.routers import coach, diary, review
from backend.services import embeddings


def scored(day, mood=None):
    return Entry(entry_date=day, mood=mood, title="", raw_text="")


# ---------------------------------------------------------- embeddings ---


def test_vectors_survive_packing():
    vector = [0.5, -1.25, 3.0]  # exactly representable as float32

    assert embeddings.unpack(embeddings.pack(vector)) == vector


def test_cosine_similarity():
    assert embeddings._cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert embeddings._cosine([1, 0], [0, 1]) == 0.0
    assert embeddings._cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert embeddings._cosine([2, 2], [5, 5]) == pytest.approx(1.0)  # length does not matter
    assert embeddings._cosine([0, 0], [1, 0]) == 0.0  # no division by zero


def test_search_ranks_by_similarity_limits_results_and_skips_unembedded_entries(db, net, add_entry):
    net.embed_rules = [("query", [1.0, 0.0, 0.0])]
    add_entry(title="far", vector=[0.0, 1.0, 0.0])
    add_entry(title="near", vector=[1.0, 0.1, 0.0])
    add_entry(title="exact", vector=[1.0, 0.0, 0.0])
    add_entry(title="no embedding")

    hits = run(embeddings.search(db, "query", top_k=2))

    assert [entry.title for entry, _ in hits] == ["exact", "near"]
    assert hits[0][1] == pytest.approx(1.0)


def test_search_finds_nothing_when_the_question_cannot_be_embedded(db, net, add_entry):
    add_entry(vector=[1.0, 0.0, 0.0])
    net.ollama_up = False

    assert run(embeddings.search(db, "query")) == []


def test_context_blocks_use_the_polished_text_and_name_the_topic(add_entry):
    polished = add_entry(title="Garden", text="raw", polished="Polished", day=date(2026, 3, 5), topic="Personal")
    plain = add_entry(title="No topic", text="raw only", day=date(2026, 3, 6))

    assert embeddings.context_block(polished) == "Entry 2026-03-05 [Personal] — Garden\nPolished"
    assert embeddings.context_block(plain) == "Entry 2026-03-06 — No topic\nraw only"


# --------------------------------------------------------------- coach ---


def test_parse_ym_accepts_a_valid_month():
    assert coach._parse_ym("2026-03") == (2026, 3)
    assert coach._parse_ym("2026-3") == (2026, 3)


@pytest.mark.parametrize("bad", [None, "", "2026-13", "2026-00", "garbage", "2026", "2026-03-01"])
def test_parse_ym_falls_back_to_the_current_month(bad):
    today = date.today()

    assert coach._parse_ym(bad) == (today.year, today.month)


def test_mood_summary_is_empty_without_scores():
    assert coach._mood_summary([scored(date(2026, 3, 1)), scored(date(2026, 3, 2))]) == ""


def test_mood_summary_averages_per_day_and_names_rough_and_great_days():
    entries = [
        scored(date(2026, 3, 3), 5),
        scored(date(2026, 3, 3), 3),  # the 3rd averages 4.0
        scored(date(2026, 3, 9), 2),
        scored(date(2026, 3, 20), 4),
    ]

    assert coach._mood_summary(entries) == (
        "3 of the month's days have mood scores. Average 3.3/5.\n"
        "Rough days (mood <= 2): March 09\n"
        "Great days (mood >= 4): March 03, March 20"
    )


@pytest.mark.parametrize(
    "moods, trend",
    [
        ([2, 2, 4, 4], "improving (first half 2.0, second half 4.0)"),
        ([4, 4, 2, 2], "declining (first half 4.0, second half 2.0)"),
        ([3, 4, 4, 3], "steady (first half 3.5, second half 3.5)"),
        ([2, 2, 2, 4, 4], "improving (first half 2.0, second half 3.3)"),  # odd number of days
        ([3, 3, 3, 3, 3, 3, 4], "steady (first half 3.0, second half 3.2)"),  # a rise of 0.25 is noise
        ([3, 3, 3, 4, 3, 3, 3, 3], "steady (first half 3.2, second half 3.0)"),  # so is a fall of 0.25
    ],
)
def test_mood_summary_reports_a_trend_from_four_or_more_scored_days(moods, trend):
    entries = [scored(date(2026, 3, day), mood) for day, mood in enumerate(moods, start=1)]

    assert coach._mood_summary(entries).splitlines()[-1] == f"Trend across the month: {trend}."


def test_mood_summary_has_no_trend_below_four_scored_days():
    entries = [scored(date(2026, 3, day), mood) for day, mood in enumerate([1, 3, 5], start=1)]

    assert "Trend" not in coach._mood_summary(entries)


# -------------------------------------------------------------- review ---


def test_the_week_strip_covers_seven_days_oldest_first_with_rounded_averages():
    today = date(2026, 3, 10)
    entries = [scored(today, 4), scored(today, 5), scored(today, 5), scored(today - timedelta(days=2), 2)]

    days = review._mood_days(entries, today)

    assert [d["date"] for d in days] == [today - timedelta(days=n) for n in range(6, -1, -1)]
    assert [d["mood"] for d in days] == [None, None, None, None, 2, None, 5]


def test_reviews_are_cached_per_iso_week():
    assert review._week_key(date(2026, 1, 1)) == "review:2026-W01"
    assert review._week_key(date(2027, 1, 1)) == "review:2026-W53"  # ISO year differs from the calendar year


# ---------------------------------------------------------- on this day ---


def test_on_this_day_lists_earlier_years_only_newest_first_and_at_most_three(db, add_entry):
    for year in (2022, 2023, 2024, 2025):
        add_entry(title=f"y{year}", day=date(year, 3, 5))
    add_entry(title="this year", day=date(2026, 3, 5))
    add_entry(title="another day", day=date(2025, 3, 6))

    memories = diary._on_this_day(db, date(2026, 3, 5))

    assert [entry.title for entry in memories] == ["y2025", "y2024", "y2023"]
