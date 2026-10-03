"""PDF export: downloads work for every scope and never fail on awkward content."""
from datetime import date

import pytest

from backend.models import Setting
from backend.services import pdf

AWKWARD = (
    "Smart “quotes” — emoji \U0001f600 arrows → bullets • café 中文\n\n"
    "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
    "```python\nprint('x')\n```\n\n"
    "![image](http://example.invalid/x.png)\n\n"
    "<script>alert(1)</script> <b>bold</b> <unknown-tag>text</unknown-tag>\n\n"
    + "w" * 400  # one very long unbroken word
)


def assert_pdf(response, filename):
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{filename}"'
    assert response.content.startswith(b"%PDF-")
    assert response.content.rstrip().endswith(b"%%EOF")


def test_every_export_scope_returns_a_pdf(client, db, add_entry):
    add_entry(title="Garden", text="Planted tomatoes", day=date(2026, 3, 5), topic="Personal", mood=4)
    topic = add_entry(title="Work", text="Shipped", day=date(2026, 3, 6), topic="Work").topic_id

    assert_pdf(client.get("/export/day/2026-03-05.pdf"), "diary-2026-03-05.pdf")
    assert_pdf(client.get("/export/month/2026/3.pdf"), "diary-2026-03.pdf")
    assert_pdf(client.get("/export/all.pdf"), "diary-all.pdf")
    assert_pdf(client.get(f"/export/topic/{topic}.pdf"), "diary-topic-work-all.pdf")
    assert_pdf(client.get(f"/export/topic/{topic}.pdf?scope=2026-03"), "diary-topic-work-2026-03.pdf")


def test_exports_of_an_empty_period_are_still_valid_pdfs(client):
    assert_pdf(client.get("/export/day/2026-03-05.pdf"), "diary-2026-03-05.pdf")
    assert_pdf(client.get("/export/all.pdf"), "diary-all.pdf")


def test_a_cached_topic_summary_does_not_break_the_topic_export(client, db, add_entry):
    topic = add_entry(title="Work", text="Shipped", topic="Work").topic_id
    db.add(Setting(key=f"topic-summary:{topic}:all", value="**Summary** with “quotes”"))
    db.commit()

    assert_pdf(client.get(f"/export/topic/{topic}.pdf"), "diary-topic-work-all.pdf")


def test_awkward_entry_text_never_makes_an_export_fail(client, add_entry):
    add_entry(title="Café \U0001f600 — 中文", text=AWKWARD, day=date(2026, 3, 5))
    add_entry(title="Polished", text="raw", polished=AWKWARD, day=date(2026, 3, 5))

    assert_pdf(client.get("/export/day/2026-03-05.pdf"), "diary-2026-03-05.pdf")
    assert_pdf(client.get("/export/all.pdf"), "diary-all.pdf")


@pytest.mark.parametrize(
    "path, status",
    [
        ("/export/day/not-a-date.pdf", 400),
        ("/export/month/2026/13.pdf", 400),
        ("/export/month/2026/0.pdf", 400),
        ("/export/topic/9999.pdf", 404),
    ],
)
def test_bad_export_requests_are_rejected_cleanly(client, path, status):
    assert client.get(path).status_code == status


def test_a_bad_topic_scope_is_a_400(client, add_entry):
    topic = add_entry(topic="Work").topic_id

    assert client.get(f"/export/topic/{topic}.pdf?scope=soon").status_code == 400


def test_text_is_reduced_to_what_the_core_pdf_font_can_draw():
    assert pdf._latin("“quoted” — ‘x’ … • →") == '"quoted" -- \'x\' ... - ->'
    assert pdf._latin("café \U0001f600 中") == "café  "  # latin-1 kept, the rest dropped


def test_markdown_is_converted_to_the_html_subset_fpdf_understands():
    html = pdf._md_html("**bold** and *italic*\n\n```\ncode\n```")

    assert "<b>bold</b>" in html and "<i>italic</i>" in html
    assert "<code>" not in html and "<pre>" not in html
