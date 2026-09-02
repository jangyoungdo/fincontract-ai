from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from app.prototype.pii import find_pii_spans
from app.services.source_previews import generate_pdf_source_previews, preview_path


def make_pdf() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 720, "Email test@example.com. Customer pays 5% fee.")
    canvas.save()
    return stream.getvalue()


def make_two_page_pdf() -> bytes:
    stream = BytesIO()
    canvas = Canvas(stream)
    canvas.drawString(72, 720, "First page target.")
    canvas.showPage()
    canvas.drawString(72, 720, "Second page target.")
    canvas.save()
    return stream.getvalue()


def test_pdf_preview_is_png_with_burned_redaction_and_match_highlight(tmp_path) -> None:
    result = {
        "findings": [
            {
                "finding_id": "finding:test",
                "source": {
                    "masked_text": "Email [EMAIL_1]. Customer pays 5% fee.",
                    "match_span": [33, 39],
                    "page_number": 1,
                    "_generate_pdf_preview": True,
                },
                "rule_signal": {"matched_excerpt": "5% fee"},
            }
        ],
        "candidate_findings": [],
    }
    settings = SimpleNamespace(ocr_languages="eng", ocr_timeout_seconds=15)
    enriched = generate_pdf_source_previews(
        make_pdf(), "analysis-preview", result, tmp_path, settings
    )
    source = enriched["findings"][0]["source"]
    assert source["preview_status"] == "available"
    path = preview_path(tmp_path, "analysis-preview", source["preview_ids"][0])
    assert path.read_bytes().startswith(b"\x89PNG")
    assert b"test@example.com" not in path.read_bytes()
    with Image.open(path) as image:
        assert image.width > 100
        assert image.height > 100


def test_preview_falls_back_to_masked_text_when_match_cannot_be_located(tmp_path) -> None:
    result = {
        "findings": [
            {
                "finding_id": "finding:missing",
                "source": {
                    "masked_text": "존재하지 않는 문구",
                    "match_span": [0, 10],
                    "page_number": 1,
                    "_generate_pdf_preview": True,
                },
                "rule_signal": {"matched_excerpt": "존재하지 않는 문구"},
            }
        ],
        "candidate_findings": [],
    }
    settings = SimpleNamespace(ocr_languages="eng", ocr_timeout_seconds=15)
    enriched = generate_pdf_source_previews(make_pdf(), "analysis-fallback", result, tmp_path, settings)
    assert enriched["findings"][0]["source"]["preview_status"] == "text_only"
    assert enriched["findings"][0]["source"]["preview_ids"] == []


def test_cross_page_match_creates_at_most_two_preview_images(tmp_path) -> None:
    result = {
        "findings": [
            {
                "finding_id": "finding:cross-page",
                "source": {
                    "masked_text": "First page target.\nSecond page target.",
                    "match_span": [0, 38],
                    "page_number": 1,
                    "_generate_pdf_preview": True,
                    "_preview_targets": [
                        {"page_number": 1, "text": "First page target."},
                        {"page_number": 2, "text": "Second page target."},
                    ],
                },
            }
        ],
        "candidate_findings": [],
    }
    settings = SimpleNamespace(ocr_languages="eng", ocr_timeout_seconds=15)
    enriched = generate_pdf_source_previews(
        make_two_page_pdf(),
        "analysis-cross-page",
        result,
        tmp_path,
        settings,
        ("First page target.", "Second page target."),
    )
    source = enriched["findings"][0]["source"]
    assert source["preview_status"] == "available"
    assert len(source["preview_ids"]) == 2
    assert "_preview_targets" not in source


def test_semantic_candidate_does_not_generate_pdf_preview(tmp_path) -> None:
    result = {
        "findings": [],
        "candidate_findings": [
            {
                "candidate_id": "candidate:test",
                "source": {
                    "masked_text": "Customer pays 5% fee.",
                    "match_span": [0, 21],
                    "page_number": 1,
                },
            }
        ],
    }
    settings = SimpleNamespace(ocr_languages="eng", ocr_timeout_seconds=15)
    enriched = generate_pdf_source_previews(
        make_pdf(), "analysis-candidate", result, tmp_path, settings
    )
    source = enriched["candidate_findings"][0]["source"]
    assert source["preview_status"] == "text_only"
    assert source["preview_ids"] == []
    assert not (tmp_path / "previews" / "analysis-candidate").exists()


def test_visual_redaction_labels_can_continue_across_pages() -> None:
    counters: dict[str, int] = {}
    first = find_pii_spans("Email first@example.com", counters)
    second = find_pii_spans("Email second@example.com", counters)
    assert first[0].replacement == "[EMAIL_1]"
    assert second[0].replacement == "[EMAIL_2]"
