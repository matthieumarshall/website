"""Helpers for building CSV and PDF exports of race results."""

import csv
import io
import re
from pathlib import Path

from fpdf import FPDF, FontFace

from website.models import Result

_COLUMNS = [
    ("Pos", "position"),
    ("Race No", "race_number"),
    ("Name", "athlete_name"),
    ("Time", "time"),
    ("Category", "category"),
    ("Cat Pos", "category_position"),
    ("Gender", "gender"),
    ("Gen Pos", "gender_position"),
    ("Club", "club"),
]


def filter_results(
    results: list[Result],
    category: str | None = None,
    club: str | None = None,
    gender: str | None = None,
    name: str | None = None,
) -> list[Result]:
    """Return results matching all supplied filter values (case-insensitive)."""
    filtered = results
    if category:
        filtered = [r for r in filtered if r.category == category]
    if club:
        filtered = [r for r in filtered if r.club == club]
    if gender:
        filtered = [r for r in filtered if r.gender.lower() == gender.lower()]
    if name:
        needle = name.lower()
        filtered = [r for r in filtered if needle in r.athlete_name.lower()]
    return filtered


def _safe_filename(value: str) -> str:
    """Strip characters unsafe for filenames."""
    return re.sub(r"[^\w\-. ]", "_", value).strip()


def build_csv(
    results: list[Result], race_name: str, fixture_title: str
) -> tuple[str, str]:
    """Return (csv_string, suggested_filename)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([col for col, _ in _COLUMNS])
    for r in results:
        writer.writerow(
            [
                r.position,
                r.race_number if r.race_number is not None else "",
                r.athlete_name,
                r.time,
                r.category,
                r.category_position if r.category_position is not None else "",
                r.gender,
                r.gender_position if r.gender_position is not None else "",
                r.club if r.club else "",
            ]
        )
    filename = f"{_safe_filename(race_name)}_{_safe_filename(fixture_title)}.csv"
    return buf.getvalue(), filename


def build_pdf(
    results: list[Result], race_name: str, fixture_title: str
) -> tuple[bytes, str]:
    """Return (pdf_bytes, suggested_filename)."""
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()

    # Brand colours matching website CSS tokens
    _PRIMARY = (31, 58, 95)  # --brand-primary  #1f3a5f
    _ACCENT = (107, 79, 58)  # --brand-accent   #6b4f3a
    _BG = (247, 245, 242)  # --brand-bg       #f7f5f2
    _TEXT = (26, 26, 46)  # --brand-text     #1a1a2e

    # Title
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_PRIMARY)
    pdf.cell(0, 8, f"{fixture_title} - {race_name}", new_x="LMARGIN", new_y="NEXT")
    # Accent rule under title
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.5)
    x_left = pdf.get_x()
    y = pdf.get_y()
    pdf.line(x_left, y, x_left + 277, y)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(3)

    # Column widths (landscape A4 = 277 mm usable)
    col_widths = [14, 18, 60, 22, 42, 16, 22, 16, 60]
    row_height = 6

    # Header row — brand-primary background, white text
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*_PRIMARY)
    pdf.set_text_color(255, 255, 255)
    for (header, _), w in zip(_COLUMNS, col_widths):
        pdf.cell(w, row_height, header, border=1, fill=True)
    pdf.ln()

    # Data rows with alternating background
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(*_TEXT)
    for i, r in enumerate(results):
        fill = i % 2 == 1
        if fill:
            pdf.set_fill_color(*_BG)
        else:
            pdf.set_fill_color(255, 255, 255)
        values = [
            str(r.position),
            str(r.race_number) if r.race_number is not None else "",
            r.athlete_name,
            r.time,
            r.category,
            str(r.category_position) if r.category_position is not None else "",
            r.gender,
            str(r.gender_position) if r.gender_position is not None else "",
            r.club if r.club else "",
        ]
        for val, w in zip(values, col_widths):
            # Truncate to fit cell; fpdf2 doesn't wrap in cell() without multi_cell
            max_chars = max(1, int(w / 2))
            display = val[:max_chars] if len(val) > max_chars else val
            pdf.cell(w, row_height, display, border=1, fill=True)
        pdf.ln()

    filename = f"{_safe_filename(race_name)}_{_safe_filename(fixture_title)}.pdf"
    raw = pdf.output()
    return bytes(raw) if raw is not None else b"", filename


def build_rules_pdf(html_content: str) -> bytes:
    """Render the rules-and-constitution HTML content to an A4 portrait PDF."""
    from fpdf.html import HTMLMixin  # noqa: PLC0415 — local import to avoid circular

    class _RulesPDF(FPDF, HTMLMixin):
        pass

    _FONT_PATH = Path("static/fonts/dm-sans.ttf")

    pdf = _RulesPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=20, top=20, right=20)

    if _FONT_PATH.exists():
        # fpdf2.add_font() accepts 'uni' parameter for Unicode support, but type stubs don't recognize it
        pdf.add_font("DM Sans", style="", fname=str(_FONT_PATH), uni=True)  # type: ignore[unknown-argument]  # ty:ignore[unknown-argument]
        pdf.add_font("DM Sans", style="B", fname=str(_FONT_PATH), uni=True)  # type: ignore[unknown-argument]  # ty:ignore[unknown-argument]
        pdf.add_font("DM Sans", style="I", fname=str(_FONT_PATH), uni=True)  # type: ignore[unknown-argument]  # ty:ignore[unknown-argument]
        pdf.add_font("DM Sans", style="BI", fname=str(_FONT_PATH), uni=True)  # type: ignore[unknown-argument]  # ty:ignore[unknown-argument]
        pdf.set_font("DM Sans", size=11)
    else:
        pdf.set_font("Helvetica", size=11)

    # Brand colours matching website CSS tokens
    _PRIMARY = (31, 58, 95)  # --brand-primary  #1f3a5f
    _ACCENT = (107, 79, 58)  # --brand-accent   #6b4f3a
    _TEXT = (26, 26, 46)  # --brand-text     #1a1a2e

    pdf.add_page()

    # Branded title block
    font_family = "DM Sans" if _FONT_PATH.exists() else "Helvetica"
    pdf.set_font(font_family, "B", 16)
    pdf.set_text_color(*_PRIMARY)
    pdf.cell(0, 10, "Rules and Constitution", new_x="LMARGIN", new_y="NEXT")
    # Accent rule under title
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.5)
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + usable_width, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.set_draw_color(0, 0, 0)
    pdf.ln(4)

    # Default body text to brand-text; HTML inline colours override this where present.
    # Heading tag_styles override fpdf2's built-in red (#800000) heading defaults.
    pdf.set_font(font_family, size=11)
    pdf.set_text_color(*_TEXT)
    _heading_style = FontFace(color=_PRIMARY)
    pdf.write_html(
        html_content,
        tag_styles={f"h{i}": _heading_style for i in range(1, 7)},
    )
    raw = pdf.output()
    return bytes(raw) if raw is not None else b""
