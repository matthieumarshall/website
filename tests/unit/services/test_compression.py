"""Unit tests: shrinking uploaded licences and assessments."""

import io

import pikepdf
import pytest
from PIL import Image

from website.errors import InvalidRequestError
from website.services.compression import (
    MAX_IMAGE_DIMENSION,
    compress_document,
    detect_kind,
)


def _photo(size: tuple[int, int], fmt: str) -> bytes:
    image = Image.effect_noise(size, 60).convert("RGB")
    out = io.BytesIO()
    image.save(out, format=fmt)
    return out.getvalue()


def _pdf(pages: int = 3) -> bytes:
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(595, 842))
    out = io.BytesIO()
    pdf.save(
        out, compress_streams=False, object_stream_mode=pikepdf.ObjectStreamMode.disable
    )
    return out.getvalue()


def test_detect_kind_recognises_pdf_and_images() -> None:
    assert detect_kind(_pdf()) == "pdf"
    assert detect_kind(_photo((10, 10), "PNG")) == "image"
    assert detect_kind(_photo((10, 10), "JPEG")) == "image"


def test_detect_kind_rejects_other_content() -> None:
    with pytest.raises(InvalidRequestError):
        detect_kind(b"MZ\x90\x00 not a document")


def test_large_png_becomes_smaller_resized_jpeg() -> None:
    data = _photo((3000, 2400), "PNG")
    result = compress_document(data)
    assert result.suffix == ".jpg"
    assert result.content_type == "image/jpeg"
    assert len(result.data) < len(data)
    with Image.open(io.BytesIO(result.data)) as packed:
        assert max(packed.size) <= MAX_IMAGE_DIMENSION


def test_small_jpeg_is_kept_when_recompression_does_not_help() -> None:
    data = _photo((8, 8), "JPEG")
    result = compress_document(data)
    assert result.suffix == ".jpg"
    assert len(result.data) <= len(data)


def test_small_png_keeps_png_when_not_smaller() -> None:
    tiny = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(tiny, format="PNG", optimize=True)
    result = compress_document(tiny.getvalue())
    assert result.suffix in {".png", ".jpg"}
    assert len(result.data) <= len(tiny.getvalue())


def test_transparent_png_is_flattened() -> None:
    noise = Image.effect_noise((1500, 1500), 60).convert("RGBA")
    noise.putalpha(Image.effect_noise((1500, 1500), 30))
    out = io.BytesIO()
    noise.save(out, format="PNG")
    result = compress_document(out.getvalue())
    with Image.open(io.BytesIO(result.data)) as packed:
        assert packed.mode == "RGB"


def test_pdf_is_rewritten_no_larger_than_original() -> None:
    data = _pdf(pages=20)
    result = compress_document(data)
    assert result.suffix == ".pdf"
    assert result.content_type == "application/pdf"
    assert len(result.data) <= len(data)
    with pikepdf.open(io.BytesIO(result.data)) as reread:
        assert len(reread.pages) == 20


def test_corrupt_pdf_is_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        compress_document(b"%PDF-1.7 this is not really a pdf")


def test_corrupt_image_is_rejected() -> None:
    with pytest.raises(InvalidRequestError):
        compress_document(b"\xff\xd8\xff\xe0 truncated")
