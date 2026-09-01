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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_NAME = "HYSMyeongJo-Medium"


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
                ["추가 검토 후보", str(len(candidate_findings))],
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

    if not findings:
        story.extend([
            Paragraph("실험 규칙 신호 없음", heading),
            Paragraph("현재 14개 실험 규칙에서 위험 신호가 탐지되지 않았습니다. 이는 계약의 안전성이나 적법성을 보장하지 않습니다.", warning),
        ])

    for index, finding in enumerate(findings, start=1):
        signal = finding.get("rule_signal", {})
        explanation = finding.get("explanation", {})
        clause = finding.get("clause", {})
        clause_number = clause.get("number")
        label = clause.get("label") or (f"제{clause_number}조" if clause_number else "")
        subclause_label = clause.get("subclause_label")
        prefix = f"{label}{f' · {subclause_label}' if subclause_label else ''} · " if label else ""
        story.extend([
            Paragraph(f"{index}. {escape(prefix + str(signal.get('rule_name', signal.get('category', '검토 신호'))))}", heading),
            Paragraph("정확히 탐지된 문구", subheading),
            _highlighted_source(finding, quote),
            Paragraph("왜 문제 후보인가", subheading),
            _paragraph(explanation.get("why_flagged"), body),
            Paragraph("예상되는 고객 영향", subheading),
            _paragraph(explanation.get("possible_impact"), body),
            Paragraph("반대 사정과 확인 조건", subheading),
        ])
        for point in explanation.get("review_points", []):
            story.append(_paragraph(f"• {point}", body))
        story.extend([
            Paragraph("검토용 대안 조항", subheading),
            _paragraph(explanation.get("suggested_revision"), revision),
            _paragraph(explanation.get("disclaimer"), body),
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

        assessment = finding.get("assessment") or {}
        if assessment:
            story.extend([
                Paragraph("AI 보충 검토", subheading),
                _paragraph(assessment.get("summary"), body),
                _paragraph(assessment.get("rationale"), body),
            ])
            for item in assessment.get("counter_considerations", []):
                story.append(_paragraph(f"• 반대 고려사항: {item}", body))
            for item in assessment.get("review_questions", []):
                story.append(_paragraph(f"• 확인 질문: {item}", body))

        verification = finding.get("verification", {})
        grounding = finding.get("grounding", {})
        story.extend([
            Paragraph("검증 상세", subheading),
            _paragraph(
                f"상태 {verification.get('status', 'not_run')} · 규칙 {signal.get('rule_id', '미상')} / {signal.get('rule_version', '미상')} · corpus {grounding.get('corpus_version', '미상')}",
                body,
            ),
        ])
        for issue in verification.get("issues", []):
            story.append(_paragraph(f"• {issue.get('code', 'VERIFY_ERROR')}: {issue.get('message', '')}", warning))

    if candidate_findings:
        story.append(Paragraph("추가 검토 후보", heading))
        story.append(_paragraph("아래 항목은 결정론 규칙 신호가 아니라 로컬 분류 사전 기반 후보입니다. 법률 판단이나 확정 신호로 사용하지 않습니다.", warning))
        for candidate in candidate_findings:
            clause = candidate.get("clause", {})
            label = clause.get("label") or f"제{clause.get('number', '?')}조"
            story.extend([
                Paragraph(f"{escape(label)} · {escape(str(candidate.get('name', '검토 후보')))}", subheading),
                _paragraph(candidate.get("source", {}).get("masked_text"), quote),
                _paragraph(f"겹친 분류 용어: {', '.join(candidate.get('matched_terms', []))}", body),
            ])
            for question in candidate.get("review_questions", []):
                story.append(_paragraph(f"• 확인 질문: {question}", body))

    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
