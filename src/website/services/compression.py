"""Shrink uploaded licences and assessments before they are stored."""

import io

import pikepdf
from PIL import Image, ImageOps, UnidentifiedImageError

from website.errors import InvalidRequestError

MAX_IMAGE_DIMENSION = 2000
JPEG_QUALITY = 80
_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


class CompressedDocument:
    """Compressed bytes together with the stored suffix and content type."""

    __slots__ = ("content_type", "data", "suffix")

    def __init__(self, data: bytes, suffix: str, content_type: str) -> None:
        """Hold the compressed *data* and how it should be stored and served."""
        self.data = data
        self.suffix = suffix
        self.content_type = content_type


def detect_kind(data: bytes) -> str:
    """Return ``"pdf"`` or ``"image"`` from the file's leading bytes.

    Raises:
        InvalidRequestError: If the content is neither a PDF, JPEG nor PNG.
    """
    if data.startswith(_PDF_MAGIC):
        return "pdf"
    if data.startswith((_PNG_MAGIC, _JPEG_MAGIC)):
        return "image"
    raise InvalidRequestError("Only PDF, JPEG or PNG files are accepted")


def _compress_pdf(data: bytes) -> bytes:
    try:
        with pikepdf.open(io.BytesIO(data)) as pdf:
            out = io.BytesIO()
            pdf.remove_unreferenced_resources()
            pdf.save(
                out,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                recompress_flate=True,
                linearize=False,
            )
    except pikepdf.PdfError as exc:
        raise InvalidRequestError("The PDF could not be read") from exc
    return out.getvalue()


def _compress_image(data: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
            if image.mode in ("RGBA", "LA", "P"):
                rgba = image.convert("RGBA")
                flat = Image.new("RGB", rgba.size, "white")
                flat.paste(rgba, mask=rgba.getchannel("A"))
                image = flat
            else:
                image = image.convert("RGB")
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidRequestError("The image could not be read") from exc
    return out.getvalue()


def compress_document(data: bytes) -> CompressedDocument:
    """Compress a PDF, JPEG or PNG, keeping the original if that is smaller.

    Images become resized JPEGs; PDFs are rewritten losslessly with compressed
    streams.

    Raises:
        InvalidRequestError: If the file is not a readable PDF, JPEG or PNG.
    """
    if detect_kind(data) == "pdf":
        packed = _compress_pdf(data)
        return CompressedDocument(
            packed if len(packed) < len(data) else data, ".pdf", "application/pdf"
        )
    packed = _compress_image(data)
    if len(packed) < len(data):
        return CompressedDocument(packed, ".jpg", "image/jpeg")
    if data.startswith(_PNG_MAGIC):
        return CompressedDocument(data, ".png", "image/png")
    return CompressedDocument(data, ".jpg", "image/jpeg")
