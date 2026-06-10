"""PDF export built on fpdf2 core fonts (Helvetica).

Core fonts are latin-1 only, so all text is sanitized first: smart punctuation
is mapped to ASCII and anything else unencodable (emoji...) is dropped. Entry
bodies are markdown - they go through the same `markdown` lib used by the web
UI, then a small tag cleanup so fpdf2's write_html accepts them. Exports must
never fail on content: prefer a slightly plainer PDF over a 500.
"""
import re

import markdown as md
from fpdf import FPDF

from ..models import Entry

_SMART = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "--", "…": "...", " ": " ",
    "•": "-", "→": "->",
}


def _latin(text: str) -> str:
    for bad, good in _SMART.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "ignore").decode("latin-1")


def _md_html(text: str) -> str:
    """Markdown -> the small HTML subset fpdf2's write_html understands."""
    html = md.markdown(text or "", extensions=["nl2br"])
    html = html.replace("<strong>", "<b>").replace("</strong>", "</b>")
    html = html.replace("<em>", "<i>").replace("</em>", "</i>")
    # keep the text, drop tags write_html may not handle
    html = re.sub(r"</?(code|pre|blockquote|table|thead|tbody|tr|td|th|img[^>]*)>", "", html)
    return _latin(html)


class _DiaryPDF(FPDF):
    def __init__(self, doc_title: str):
        super().__init__(format="A4")
        self.doc_title = _latin(doc_title)
        self.set_title(self.doc_title)
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 18, 18)

    def header(self):
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150, 145, 138)
        self.cell(0, 6, self.doc_title, align="L")
        self.ln(10)

    def footer(self):
        self.set_y(-14)
        self.set_font("helvetica", "I", 8)
        self.set_text_color(150, 145, 138)
        self.cell(0, 6, f"{self.page_no()}/{{nb}}", align="C")

    def para(self, height: float, text: str) -> None:
        # full-width multi_cell that returns the cursor to the left margin
        self.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")


def _entry_block(pdf: _DiaryPDF, e: Entry) -> None:
    pdf.set_text_color(30, 26, 22)
    pdf.set_font("helvetica", "B", 12)
    pdf.para(6, _latin(e.title or "Untitled"))
    meta = [e.created_at.strftime("%H:%M")]
    if e.topic:
        meta.append(e.topic.name)
    if e.mood:
        meta.append(f"mood {e.mood}/5")
    if e.polished_text:
        meta.append("polished")
    pdf.set_font("helvetica", "I", 8.5)
    pdf.set_text_color(140, 134, 126)
    pdf.para(5, _latin(" - ".join(meta)))
    pdf.ln(1)
    pdf.set_font("helvetica", "", 10.5)
    pdf.set_text_color(45, 40, 35)
    pdf.write_html(_md_html(e.display_text))
    pdf.ln(7)


def _markdown_block(pdf: _DiaryPDF, text: str) -> None:
    pdf.set_font("helvetica", "", 10.5)
    pdf.set_text_color(45, 40, 35)
    pdf.write_html(_md_html(text))
    pdf.ln(7)


def entries_pdf(
    title: str,
    subtitle: str,
    groups: list[tuple[str, list[Entry]]],
    intro_heading: str = "",
    intro_md: str = "",
) -> bytes:
    """One PDF: big title, optional AI-written intro, then grouped entries.

    groups: (label, entries) - label may be "" for a single flat list.
    """
    pdf = _DiaryPDF(title)
    pdf.add_page()

    pdf.set_font("helvetica", "B", 22)
    pdf.set_text_color(30, 26, 22)
    pdf.para(10, _latin(title))
    if subtitle:
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(140, 134, 126)
        pdf.para(6, _latin(subtitle))
    pdf.ln(4)

    if intro_md:
        if intro_heading:
            pdf.set_font("helvetica", "B", 13)
            pdf.set_text_color(224, 82, 29)
            pdf.para(7, _latin(intro_heading))
            pdf.ln(1)
        _markdown_block(pdf, intro_md)
        pdf.ln(2)

    total = sum(len(es) for _, es in groups)
    if total == 0:
        pdf.set_font("helvetica", "I", 11)
        pdf.set_text_color(140, 134, 126)
        pdf.para(6, "No entries in this period.")
    for label, entries in groups:
        if not entries:
            continue
        if label:
            pdf.set_font("helvetica", "B", 13)
            pdf.set_text_color(224, 82, 29)
            pdf.para(7, _latin(label))
            pdf.set_draw_color(224, 82, 29)
            pdf.set_line_width(0.4)
            pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + 40, pdf.get_y() + 1)
            pdf.ln(5)
        for e in entries:
            _entry_block(pdf, e)

    return bytes(pdf.output())
