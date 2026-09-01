"""Create irreversible, privacy-masked PNG excerpts from uploaded PDF pages."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.prototype.pii import find_pii_spans

RENDER_SCALE = 2.0
MAX_CROP_PAGE_RATIO = 0.40
LOGGER = logging.getLogger(__name__)


def _normalized_with_indexes(text: str) -> tuple[str, list[int]]:
    normalized: list[str] = []
    indexes: list[int] = []
    for index, character in enumerate(text):
        if character.isspace():
            continue
        normalized.append(character.casefold())
        indexes.append(index)
    return "".join(normalized), indexes


def _locate(text: str, target: str) -> tuple[int, int] | None:
    """Find text despite PDF line-break and spacing differences."""
    compact_text, indexes = _normalized_with_indexes(text)
    compact_target, _ = _normalized_with_indexes(target)
    if not compact_target:
        return None
    start = compact_text.find(compact_target)
    if start < 0:
        return None
    end = start + len(compact_target) - 1
    return indexes[start], indexes[end] + 1


def _pdf_rect_to_pixels(box: tuple[float, float, float, float], page_height: float) -> tuple[int, int, int, int]:
    left, bottom, right, top = box
    return (
        int(left * RENDER_SCALE),
        int((page_height - top) * RENDER_SCALE),
        int(right * RENDER_SCALE) + 1,
        int((page_height - bottom) * RENDER_SCALE) + 1,
    )


def _union(rectangles: Iterable[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    values = list(rectangles)
    if not values:
        return None
    return (
        min(item[0] for item in values),
        min(item[1] for item in values),
        max(item[2] for item in values),
        max(item[3] for item in values),
    )


def _native_layout(
    text_page: Any, page_height: float
) -> tuple[str, Callable[[int, int], list[tuple[int, int, int, int]]]]:
    text = text_page.get_text_bounded()

    def boxes(start: int, end: int) -> list[tuple[int, int, int, int]]:
        rectangles = []
        for index in range(max(0, start), min(end, text_page.count_chars())):
            try:
                rectangles.append(_pdf_rect_to_pixels(text_page.get_charbox(index), page_height))
            except Exception as exc:  # noqa: BLE001 - one malformed glyph must not expose PII
                LOGGER.debug("PDF character box unavailable", exc_info=exc)
                continue
        return rectangles

    return text, boxes


def _ocr_layout(
    image: Image.Image, settings: Any
) -> tuple[str, Callable[[int, int], list[tuple[int, int, int, int]]]]:
    import pytesseract

    data = pytesseract.image_to_data(
        image,
        lang=settings.ocr_languages,
        config="--oem 1 --psm 6",
        timeout=settings.ocr_timeout_seconds,
        output_type=pytesseract.Output.DICT,
    )
    parts: list[str] = []
    tokens: list[tuple[int, int, tuple[int, int, int, int]]] = []
    cursor = 0
    for index, raw in enumerate(data.get("text", [])):
        token = str(raw).strip()
        if not token:
            continue
        if parts:
            cursor += 1
        start = cursor
        parts.append(token)
        cursor += len(token)
        left = int(data["left"][index])
        top = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])
        tokens.append((start, cursor, (left, top, left + width, top + height)))
    text = " ".join(parts)

    def boxes(start: int, end: int) -> list[tuple[int, int, int, int]]:
        return [box for token_start, token_end, box in tokens if token_start < end and token_end > start]

    return text, boxes


def _draw_redactions(
    image: Image.Image,
    layout_text: str,
    boxes,
    counters: dict[str, int] | None = None,
) -> bool:
    """Burn every detected identifier into pixels; fail closed if one has no box."""
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default()
    for span in find_pii_spans(layout_text, counters):
        rectangle = _union(boxes(span.start, span.end))
        if rectangle is None:
            return False
        draw.rectangle(rectangle, fill=(20, 28, 40, 255))
        draw.text((rectangle[0] + 3, rectangle[1] + 2), span.replacement, fill=(255, 255, 255, 255), font=font)
    return True


def _crop_and_highlight(
    image: Image.Image,
    match_rectangles: list[tuple[int, int, int, int]],
) -> Image.Image | None:
    match_union = _union(match_rectangles)
    if match_union is None:
        return None
    draw = ImageDraw.Draw(image, "RGBA")
    for rectangle in match_rectangles:
        draw.rectangle(rectangle, fill=(255, 208, 64, 95), outline=(220, 146, 0, 210), width=2)
    width, height = image.size
    crop_height = max(180, int(height * MAX_CROP_PAGE_RATIO))
    center_y = (match_union[1] + match_union[3]) // 2
    top = max(0, min(height - crop_height, center_y - crop_height // 2))
    side = max(8, int(width * 0.025))
    return image.crop((side, top, width - side, min(height, top + crop_height)))


def _target_text(item: dict) -> str:
    source = item.get("source", {})
    text = str(source.get("masked_text", ""))
    span = source.get("match_span", [0, 0])
    try:
        start, end = int(span[0]), int(span[1])
    except (IndexError, TypeError, ValueError):
        start, end = 0, 0
    if 0 <= start < end <= len(text):
        return text[start:end]
    return str(item.get("rule_signal", {}).get("matched_excerpt") or text[:120])


def preview_path(report_dir: Path, analysis_id: str, preview_id: str) -> Path:
    """Resolve only opaque, hash-derived preview identifiers beneath the report root."""
    if not re.fullmatch(r"[a-f0-9]{24}", preview_id):
        raise ValueError("invalid preview id")
    return report_dir / "previews" / analysis_id / f"{preview_id}.png"


def generate_pdf_source_previews(
    data: bytes,
    analysis_id: str,
    result: dict,
    report_dir: Path,
    settings,
    pages: tuple[str, ...] | None = None,
) -> dict:
    """Generate up to two sanitized page crops per item without changing detections."""
    import pypdfium2 as pdfium

    target_dir = report_dir / "previews" / analysis_id
    shutil.rmtree(target_dir, ignore_errors=True)
    document = pdfium.PdfDocument(data)
    page_counters: list[dict[str, int]] = []
    counters: dict[str, int] = {}
    for page_text in pages or ():
        page_counters.append(dict(counters))
        find_pii_spans(page_text, counters)
    try:
        for item in [*result.get("findings", []), *result.get("candidate_findings", [])]:
            source = item.setdefault("source", {})
            source["preview_status"] = "text_only"
            source["preview_ids"] = []
            raw_targets = source.pop("_preview_targets", None)
            targets = raw_targets if isinstance(raw_targets, list) and raw_targets else [
                {"page_number": source.get("page_number"), "text": _target_text(item)}
            ]
            for target_index, target in enumerate(targets[:2]):
                page_number = target.get("page_number")
                target_text = str(target.get("text", ""))
                if not isinstance(page_number, int) or not 1 <= page_number <= len(document):
                    continue
                page = document[page_number - 1]
                text_page = None
                bitmap = None
                try:
                    _, page_height = page.get_size()
                    bitmap = page.render(scale=RENDER_SCALE)
                    image = bitmap.to_pil().convert("RGB")
                    text_page = page.get_textpage()
                    layout_text, boxes = _native_layout(text_page, page_height)
                    if not layout_text.strip():
                        layout_text, boxes = _ocr_layout(image, settings)
                    located = _locate(layout_text, target_text)
                    if located is None:
                        continue
                    starting_counts = (
                        dict(page_counters[page_number - 1])
                        if page_number <= len(page_counters)
                        else None
                    )
                    if not _draw_redactions(image, layout_text, boxes, starting_counts):
                        continue
                    cropped = _crop_and_highlight(image, boxes(*located))
                    if cropped is None:
                        continue
                    item_id = str(item.get("finding_id") or item.get("candidate_id") or "source")
                    identity = f"{item_id}:{page_number}:{target_index}"
                    preview_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
                    target_dir.mkdir(parents=True, exist_ok=True)
                    cropped.save(
                        preview_path(report_dir, analysis_id, preview_id),
                        format="PNG",
                        optimize=True,
                    )
                    source["preview_ids"].append(preview_id)
                except Exception as exc:  # noqa: BLE001 - preview failure falls back to masked text
                    LOGGER.warning(
                        "Source preview generation fell back to masked text",
                        extra={"analysis_id": analysis_id, "page_number": page_number},
                        exc_info=exc,
                    )
                finally:
                    if text_page is not None:
                        text_page.close()
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
            if source["preview_ids"]:
                source["preview_status"] = "available"
    finally:
        document.close()
    return result


def delete_preview_tree(report_dir: Path, analysis_id: str) -> None:
    """Remove only the opaque analysis preview directory."""
    target = report_dir / "previews" / analysis_id
    shutil.rmtree(target, ignore_errors=True)
