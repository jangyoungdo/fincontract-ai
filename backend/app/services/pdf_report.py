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
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_NAME = "HYSMyeongJo-Medium"


def _draw_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setFont(FONT_NAME, 8)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.drawString(document.leftMargin, 10 * mm, "FinContract AI · 계약 검토 보조")
    canvas.drawRightString(A4[0] - document.rightMargin, 10 * mm, f"페이지 {document.page}")
    canvas.restoreState()


def build_pdf_report(analysis_id: str, result: dict | None) -> bytes:
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
    body = ParagraphStyle("KoreanBody", parent=styles["BodyText"], fontName=FONT_NAME, fontSize=9, leading=14)
    heading = ParagraphStyle("KoreanHeading", parent=body, fontSize=14, leading=20, spaceBefore=10, spaceAfter=6)
    title = ParagraphStyle("KoreanTitle", parent=heading, fontSize=22, leading=28, alignment=TA_CENTER, textColor=colors.HexColor("#172554"))
    warning = ParagraphStyle("KoreanWarning", parent=body, textColor=colors.HexColor("#9A3412"), backColor=colors.HexColor("#FFF7ED"), borderPadding=8)

    safe_result = result or {}
    findings = safe_result.get("findings", [])
    story = [
        Paragraph("FinContract AI 계약 검토 리포트", title),
        Spacer(1, 6 * mm),
        Paragraph("법률 판단이 아닌 검토 보조 자료입니다. 최종 판단에는 전문가 검토가 필요합니다.", warning),
        Spacer(1, 5 * mm),
        Table(
            [
                ["분석 ID", escape(analysis_id)],
                ["상태", escape(str(safe_result.get("disposition", "unknown")))],
                ["조항 수", str(safe_result.get("clause_count", 0))],
                ["검토 신호", str(len(findings))],
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
    for index, finding in enumerate(findings, start=1):
        story.extend([
            Paragraph(f"{index}. {escape(str(finding.get('rule_signal', {}).get('category', '검토 신호')))}", heading),
            Paragraph(escape(str(finding.get("source", {}).get("masked_text", ""))), body),
            Spacer(1, 2 * mm),
            Paragraph(escape(str((finding.get("assessment") or {}).get("summary", finding.get("rule_signal", {}).get("rationale", "")))), body),
            Paragraph(f"근거 검증: {escape(str(finding.get('verification', {}).get('status', 'not_run')))}", body),
        ])
        for evidence in finding.get("evidence", []):
            story.append(Paragraph(f"- {escape(str(evidence.get('title', '근거')))} ({escape(str(evidence.get('status', 'unknown')))})", body))
        if index < len(findings) and index % 3 == 0:
            story.append(PageBreak())
    document.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buffer.getvalue()
