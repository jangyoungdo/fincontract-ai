"""Generate a Korean PDF review report from a completed analysis."""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image as ReportImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import get_settings

from .source_previews import preview_path

FONT_NAME = "HYSMyeongJo-Medium"
VERIFICATION_LABELS = {
    "passed": "법적 근거 확인",
    "failed": "법적 근거 추가 확인 필요",
    "not_run": "근거 검증 미실행",
}


def _draw_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(document.leftMargin, 10 * mm, "FinContract AI · 계약 검토 보조")
    canvas.drawRightString(A4[0] - document.rightMargin, 10 * mm, f"페이지 {document.page}")
    canvas.restoreState()


def _paragraph(value: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value or "")), style)


def _highlighted_source(finding: dict, style: ParagraphStyle) -> Paragraph:
    """Highlight only the verified match span in privacy-masked clause text."""
    source = finding.get("source", {})
    text = str(source.get("masked_text", ""))
    span = source.get("match_span", [0, 0])
    try:
        start, end = int(span[0]), int(span[1])
    except (IndexError, TypeError, ValueError):
        start, end = 0, 0
    if 0 <= start < end <= len(text):
        markup = f"{escape(text[:start])}<b><u>{escape(text[start:end])}</u></b>{escape(text[end:])}"
        return Paragraph(markup, style)
    return _paragraph(text, style)


def _preview_image(analysis_id: str, item: dict) -> ReportImage | None:
    identifiers = item.get("source", {}).get("preview_ids", [])
    if not identifiers:
        return None
    try:
        path = preview_path(get_settings().report_dir, analysis_id, str(identifiers[0]))
    except ValueError:
        return None
    if not path.is_file():
        return None
    image = ReportImage(str(path))
    scale = min((155 * mm) / image.imageWidth, (72 * mm) / image.imageHeight, 1)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    return image


def build_pdf_report(analysis_id: str, result: dict | None) -> bytes:
    """Render explanations and citations without embedding the uploaded source file."""
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="FinContract AI 검토 리포트",
        author="FinContract AI",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle("KoreanBody", parent=styles["BodyText"], fontName=FONT_NAME, fontSize=9, leading=14, spaceAfter=4)
    heading = ParagraphStyle("KoreanHeading", parent=body, fontSize=14, leading=20, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#172554"))
    subheading = ParagraphStyle("KoreanSubheading", parent=body, fontSize=10, leading=15, spaceBefore=7, spaceAfter=3, textColor=colors.HexColor("#1E3A8A"))
    title = ParagraphStyle("KoreanTitle", parent=heading, fontSize=22, leading=28, alignment=TA_CENTER)
    warning = ParagraphStyle("KoreanWarning", parent=body, textColor=colors.HexColor("#9A3412"), backColor=colors.HexColor("#FFF7ED"), borderPadding=8)
    quote = ParagraphStyle("KoreanQuote", parent=body, backColor=colors.HexColor("#F1F5F9"), borderColor=colors.HexColor("#2563EB"), borderWidth=1, borderPadding=8)
    revision = ParagraphStyle("KoreanRevision", parent=body, backColor=colors.HexColor("#EFF6FF"), borderPadding=8)

    safe_result = result or {}
    findings = safe_result.get("findings", [])
    candidate_findings = safe_result.get("candidate_findings", [])
    story = [
        Paragraph("FinContract AI 계약 검토 리포트", title),
        Spacer(1, 6 * mm),
        Paragraph("법률 판단이 아닌 검토 보조 자료입니다. 최종 판단에는 전문가 검토가 필요합니다.", warning),
        Spacer(1, 5 * mm),
        Table(
            [
                ["분석 ID", _paragraph(analysis_id, body)],
                ["상태", _paragraph(safe_result.get("disposition", "unknown"), body)],
                ["조항 수", str(safe_result.get("clause_count", 0))],
                ["검토 신호", str(len(findings))],
                ["추가 의미 검토 후보", str(len(candidate_findings))],
            ],
            colWidths=[35 * mm, 120 * mm],
            style=TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E0E7FF")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94A3B8")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]),
        ),
    ]
    summary = safe_result.get("summary", {})
    if summary.get("headline"):
        summary_lines = summary.get("lines") or [summary["headline"]]
        story.extend([Paragraph("핵심 요약", heading)])
        story.extend(_paragraph(line, quote) for line in summary_lines)

    if not findings:
        story.extend([
            Paragraph("실험 규칙 신호 없음", heading),
            Paragraph("현재 19개 규칙과 추가 의미 검토에서 위험 신호가 탐지되지 않았습니다. 이는 계약의 안전성이나 적법성을 보장하지 않습니다.", warning),
        ])

    for index, finding in enumerate(findings, start=1):
        signal = finding.get("rule_signal", {})
        explanation = finding.get("explanation", {})
        clause = finding.get("clause", {})
        clause_number = clause.get("number")
        label = clause.get("label") or (f"제{clause_number}조" if clause_number else "")
        subclause_label = clause.get("subclause_label")
        page_number = finding.get("source", {}).get("page_number")
        page_suffix = f" · PDF {page_number}페이지" if page_number else ""
        prefix = f"{label}{f' · {subclause_label}' if subclause_label else ''} · " if label else ""
        story.extend([
            Paragraph(f"{index}. {escape(prefix + str(signal.get('rule_name', signal.get('category', '검토 신호'))) + page_suffix)}", heading),
            _paragraph(finding.get("summary_sentence"), body),
            Paragraph("위험 표현이 결합된 원문 근거", subheading),
        ])
        preview = _preview_image(analysis_id, finding)
        story.extend([
            preview if preview is not None else _highlighted_source(finding, quote),
            Paragraph("탐지된 위험 구조", subheading),
            _paragraph("단일 단어가 아니라 다음 표현들이 같은 조항에 결합된 구조를 검토합니다.", body),
        ])
        for element in signal.get("matched_elements", []):
            story.append(
                _paragraph(
                    f"• {element.get('label', '판단 표현')}: {element.get('excerpt', '')}",
                    body,
                )
            )
        story.extend([
            Paragraph("왜 문제 후보인가", subheading),
            _paragraph(explanation.get("why_flagged"), body),
            Paragraph("예상되는 고객 영향", subheading),
            _paragraph(explanation.get("possible_impact"), body),
            Paragraph("반대 사정과 확인 조건", subheading),
        ])
        for point in explanation.get("review_points", []):
            story.append(_paragraph(f"• {point}", body))
        story.extend([
            Paragraph("수정 방향", subheading),
        ])
        for point in explanation.get("revision_points", explanation.get("review_points", [])):
            story.append(_paragraph(f"• {point}", body))
        story.extend([
            Paragraph("검토용 예시 문안", subheading),
            _paragraph(
                explanation.get("example_clause", explanation.get("suggested_revision")),
                revision,
            ),
            _paragraph(
                f"{explanation.get('disclaimer', '')} 실제 상품 조건과 적용 법령을 확인한 뒤 확정해야 합니다.",
                body,
            ),
            Paragraph("법적 근거 후보", subheading),
        ])
        evidence_items = finding.get("evidence", [])
        if not evidence_items:
            story.append(_paragraph("검증된 근거를 검색하지 못했습니다. 법령 원문과 시행일을 별도로 확인하세요.", warning))
        for evidence in evidence_items:
            story.extend([
                _paragraph(f"• {evidence.get('title', '근거')} · {evidence.get('authority', '기관 미상')} · {evidence.get('status', 'unknown')}", body),
                _paragraph(evidence.get("quoted_excerpt", ""), quote),
                _paragraph(f"원문: {evidence.get('source_url', '링크 없음')} · manifest {evidence.get('manifest_version', '미상')}", body),
            ])

        verification = finding.get("verification", {})
        grounding = finding.get("grounding", {})
        story.extend([
            Paragraph("검증 상세", subheading),
            _paragraph(
                f"상태 {VERIFICATION_LABELS.get(verification.get('status', 'not_run'), '근거 상태 확인 필요')} · 규칙 {signal.get('rule_id', '미상')} / {signal.get('rule_version', '미상')} · corpus {grounding.get('corpus_version', '미상')}",
                body,
            ),
        ])
        for issue in verification.get("issues", []):
            story.append(_paragraph(f"• {issue.get('code', 'VERIFY_ERROR')}: {issue.get('message', '')}", warning))

    if candidate_findings:
        story.append(Paragraph("추가 의미 검토 후보", heading))
        story.append(_paragraph("아래 항목은 결정론 규칙 신호가 아닌 로컬 의미 모델 또는 선택적 OpenAI 문맥 검토의 후보입니다. 법률 판단이나 확정 신호로 사용하지 않습니다.", warning))
        for candidate in candidate_findings:
            clause = candidate.get("clause", {})
            label = clause.get("label") or f"제{clause.get('number', '?')}조"
            if clause.get("subclause_label"):
                label = f"{label} · {clause['subclause_label']}"
            page_number = candidate.get("source", {}).get("page_number")
            if page_number:
                label = f"{label} · PDF {page_number}페이지"
            method = candidate.get("review_method", "local_e5")
            detail = (
                f"OpenAI 문맥 검토 · {candidate.get('model_id', 'OpenAI model')} · "
                f"prompt {candidate.get('model_revision', 'api-managed')}"
                if method == "openai_context"
                else (
                    f"유사도 {float(candidate.get('similarity_score', 0)):.3f} · "
                    f"{candidate.get('model_id', 'local model')} · "
                    f"리비전 {candidate.get('model_revision', 'unknown')}"
                )
            )
            story.extend([
                Paragraph(f"{escape(label)} · {escape(str(candidate.get('name', '검토 후보')))}", subheading),
                _paragraph(candidate.get("summary_sentence"), body),
                _paragraph(detail, body),
            ])
            preview = _preview_image(analysis_id, candidate)
            story.append(
                preview
                if preview is not None
                else _paragraph(candidate.get("source", {}).get("masked_text"), quote)
            )
            for question in candidate.get("review_questions", []):
                story.append(_paragraph(f"• 확인 질문: {question}", body))

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
