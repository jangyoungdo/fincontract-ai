from __future__ import annotations

from io import BytesIO

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


def extract_text(data: bytes, extension: str, max_characters: int = 200_000) -> str:
    """Extract bounded text from validated TXT, PDF, or DOCX bytes in memory."""
    if extension == ".txt":
        text = data.decode("utf-8")
    elif extension == ".pdf":
        reader = PdfReader(BytesIO(data))
        if len(reader.pages) > 200:
            raise ValueError("PDF 페이지 제한을 초과했습니다.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError(
                "OCR_REQUIRED: 텍스트가 없는 스캔 PDF입니다. OCR 처리 후 다시 업로드하세요."
            )
    elif extension == ".docx":
        document = Document(BytesIO(data))
        blocks = []
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph) and block.text.strip():
                blocks.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        blocks.append(" | ".join(cells))
        text = "\n".join(blocks)
    else:
        raise ValueError("지원하지 않는 추출 형식입니다.")

    text = text.replace("\x00", "").strip()
    if not text:
        raise ValueError("문서에서 텍스트를 추출하지 못했습니다.")
    if len(text) > max_characters:
        raise ValueError("추출 문자 수 제한을 초과했습니다.")
    return text
