from io import BytesIO
from types import SimpleNamespace

import pytesseract
import pytest
from pypdf import PdfWriter

from app.prototype.pii import mask_pii
from app.services import text_extraction


def make_blank_pdf(page_count: int = 1, *, encrypted: bool = False) -> bytes:
    """Build a deterministic PDF container without relying on OCR binaries."""
    stream = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    if encrypted:
        writer.encrypt("test-password")
    writer.write(stream)
    return stream.getvalue()


def ocr_settings(**overrides) -> SimpleNamespace:
    """Return only the bounded OCR policy consumed by text extraction."""
    values = {
        "pdf_max_pages": 50,
        "ocr_enabled": True,
        "ocr_languages": "kor+eng",
        "ocr_dpi": 200,
        "ocr_max_pixels_per_page": 8_000_000,
        "ocr_timeout_seconds": 15,
        "ocr_min_characters_per_page": 10,
        "ocr_min_alnum_ratio": 0.25,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_scanned_pdf_uses_local_ocr_and_masks_result_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the scan-to-privacy boundary without sending text externally."""
    sensitive_text = "홍길동 고객의 주민등록번호는 900101-1234567 입니다."
    monkeypatch.setattr(text_extraction, "get_settings", lambda: ocr_settings())
    monkeypatch.setattr(
        text_extraction,
        "_ocr_pdf_pages",
        lambda data, indexes, settings: {index: sensitive_text for index in indexes},
    )

    extracted = text_extraction.extract_text(make_blank_pdf(), ".pdf")
    masking = mask_pii(extracted)

    assert masking.passed
    assert "900101-1234567" not in masking.masked_text
    assert "[RESIDENT_ID_1]" in masking.masked_text


def test_ocr_quality_gate_rejects_short_or_symbol_heavy_output() -> None:
    """Fail closed when OCR output is too small or noisy to review safely."""
    assert not text_extraction._is_usable_ocr_text("가나다", 10, 0.25)
    assert not text_extraction._is_usable_ocr_text("##########가", 10, 0.25)
    assert text_extraction._is_usable_ocr_text("대출 약관 제1조 적용 조건 안내", 10, 0.25)


def test_pdf_page_limit_is_checked_before_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject oversized page sets before rendering can consume CPU or memory."""
    monkeypatch.setattr(
        text_extraction,
        "get_settings",
        lambda: ocr_settings(pdf_max_pages=1),
    )
    with pytest.raises(ValueError, match="^PDF_PAGE_LIMIT:"):
        text_extraction.extract_text(make_blank_pdf(page_count=2), ".pdf")


def test_encrypted_pdf_fails_with_stable_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Do not attempt password guessing, rendering, or OCR on encrypted PDFs."""
    monkeypatch.setattr(text_extraction, "get_settings", lambda: ocr_settings())
    with pytest.raises(ValueError, match="^PDF_ENCRYPTED:"):
        text_extraction.extract_text(make_blank_pdf(encrypted=True), ".pdf")


def test_disabled_ocr_preserves_explicit_required_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep local development fail-closed unless OCR is explicitly enabled."""
    monkeypatch.setattr(
        text_extraction,
        "get_settings",
        lambda: ocr_settings(ocr_enabled=False),
    )
    with pytest.raises(ValueError, match="^OCR_REQUIRED:"):
        text_extraction.extract_text(make_blank_pdf(), ".pdf")


def test_missing_tesseract_binary_fails_with_stable_error_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Translate host configuration failures without exposing command details."""
    monkeypatch.setattr(
        pytesseract.pytesseract,
        "tesseract_cmd",
        "/definitely-not-installed/tesseract",
    )
    with pytest.raises(ValueError, match="^OCR_UNAVAILABLE:"):
        text_extraction._ocr_pdf_pages(make_blank_pdf(), [0], ocr_settings())


def test_ocr_timeout_fails_with_stable_error_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Convert the OCR subprocess timeout into a reviewable public error code."""
    def raise_timeout(*_args, **_kwargs) -> str:
        raise RuntimeError("timeout")

    monkeypatch.setattr(pytesseract, "image_to_string", raise_timeout)
    with pytest.raises(ValueError, match="^OCR_TIMEOUT:"):
        text_extraction._ocr_pdf_pages(make_blank_pdf(), [0], ocr_settings())


def test_ocr_pixel_limit_is_checked_before_engine_call() -> None:
    """Bound rendered image memory independently from PDF byte size."""
    with pytest.raises(ValueError, match="^OCR_PIXEL_LIMIT:"):
        text_extraction._ocr_pdf_pages(
            make_blank_pdf(),
            [0],
            ocr_settings(ocr_max_pixels_per_page=1),
        )
