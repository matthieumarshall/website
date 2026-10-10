"""Shrink uploaded documents before they are stored."""

import io
import zipfile

import pikepdf
from PIL import Image, ImageOps, UnidentifiedImageError

from website.errors import InvalidRequestError

MAX_IMAGE_DIMENSION = 2000
JPEG_QUALITY = 80
_PDF_MAGIC = b"%PDF-"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_ZIP_CONTAINERS = frozenset({".zip", ".docx", ".xlsx"})
_ZIP_LEVEL = 9
_ZIP_ENCRYPTED_FLAG = 0x1


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


def _recompress_zip(data: bytes) -> bytes:
    """Re-deflate a zip container's entries at the highest level.

    Entry order, names, timestamps and stored (uncompressed) entries are kept,
    so Office documents stay valid. Encrypted archives are returned unchanged.
    """
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(data)) as source,
        zipfile.ZipFile(out, "w") as target,
    ):
        for info in source.infolist():
            if info.flag_bits & _ZIP_ENCRYPTED_FLAG:
                return data
            # compresslevel only affects deflated entries; stored ones stay so.
            target.writestr(info, source.read(info), compresslevel=_ZIP_LEVEL)
        target.comment = source.comment
    return out.getvalue()


def shrink_document(data: bytes, suffix: str) -> bytes:
    """Losslessly shrink a stored document, keeping the original if not smaller.

    PDFs are rewritten with compressed streams and zip-based files (``.zip``,
    ``.docx``, ``.xlsx``) are re-deflated. Other types, and files that cannot
    be parsed, are returned unchanged: this never rejects an upload.
    """
    suffix = suffix.lower()
    try:
        if suffix == ".pdf" and data.startswith(_PDF_MAGIC):
            packed = _compress_pdf(data)
        elif suffix in _ZIP_CONTAINERS:
            packed = _recompress_zip(data)
        else:
            return data
    except (InvalidRequestError, zipfile.BadZipFile, OSError, ValueError):
        return data
    return packed if len(packed) < len(data) else data
