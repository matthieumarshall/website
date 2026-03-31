"""Helpers for building CSV and PDF exports of race results."""

import csv
import io
import re

from fpdf import FPDF

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

    # Title
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"{fixture_title} - {race_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Column widths (landscape A4 = 277 mm usable)
    col_widths = [14, 18, 60, 22, 42, 16, 22, 16, 60]
    row_height = 6

    # Header row
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(220, 220, 220)
    for (header, _), w in zip(_COLUMNS, col_widths):
        pdf.cell(w, row_height, header, border=1, fill=True)
    pdf.ln()

    # Data rows with alternating background
    pdf.set_font("Helvetica", size=8)
    for i, r in enumerate(results):
        fill = i % 2 == 1
        if fill:
            pdf.set_fill_color(245, 245, 245)
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
