"""Render entry receipts as HTML, and as PDF via WeasyPrint."""

from pathlib import Path

from jinja2 import Environment

from website.services.entries import Receipt
from website.web.rendering import fields

RECEIPT_TEMPLATE = "entries/receipt.html"


class ReceiptRenderer:
    """Turns a :class:`Receipt` into a standalone HTML page or PDF."""

    def __init__(self, env: Environment, templates_dir: Path) -> None:
        """Use the application's Jinja environment and templates directory."""
        self._env = env
        self._templates_dir = templates_dir

    def html(self, receipt: Receipt) -> str:
        """Render the receipt as an HTML string."""
        return self._env.get_template(RECEIPT_TEMPLATE).render(**fields(receipt))

    def pdf(self, receipt: Receipt) -> bytes:
        """Render the receipt as PDF bytes."""
        # Imported lazily so WeasyPrint's system libraries are only needed here.
        from weasyprint import HTML  # noqa: PLC0415

        pdf_bytes: bytes = HTML(
            string=self.html(receipt), base_url=str(self._templates_dir)
        ).write_pdf()
        return pdf_bytes
