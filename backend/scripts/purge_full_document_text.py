#!/usr/bin/env python3
"""Remove legacy full masked-document strings from persisted analysis JSON."""

from __future__ import annotations

import json

from app.models import AnalysisRecord, get_session_factory


def main() -> int:
    updated = 0
    with get_session_factory()() as session:
        for record in session.query(AnalysisRecord).filter(AnalysisRecord.result_json.is_not(None)):
            result = json.loads(record.result_json or "{}")
            document = result.get("document")
            if not isinstance(document, dict) or "masked_text" not in document:
                continue
            document.pop("masked_text", None)
            record.result_json = json.dumps(result, ensure_ascii=False)
            updated += 1
        session.commit()
    print(json.dumps({"status": "completed", "updated_analyses": updated}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
