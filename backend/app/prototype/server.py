"""Zero-dependency local HTTP server for the prototype review workflow."""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.prototype.pipeline import PrototypePipeline  # noqa: E402

PIPELINE = PrototypePipeline()
ANALYSES: Dict[str, Dict[str, Any]] = {}
UI_PATH = REPO_ROOT / "frontend" / "prototype" / "index.html"


class PrototypeHandler(BaseHTTPRequestHandler):
    """Serve the legacy zero-dependency demo without persisting source text."""

    def do_GET(self) -> None:  # noqa: N802
        """Serve the prototype UI or retrieve one in-memory analysis."""
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/api/v1/analyses/"):
            analysis_id = path.rsplit("/", 1)[-1]
            result = ANALYSES.get(analysis_id)
            self._json(200, result) if result else self._json(404, {"error": "NOT_FOUND"})
            return
        self._json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802
        """Run an analysis or save a bounded human-review decision in memory."""
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/v1/analyses":
                result = PIPELINE.analyze(
                    payload.get("text", ""), "D"
                )
                ANALYSES[result["analysis_id"]] = result
                self._json(201, result)
                return
            if path.endswith("/review") and path.startswith("/api/v1/analyses/"):
                analysis_id = path.split("/")[-2]
                result = ANALYSES.get(analysis_id)
                if not result:
                    self._json(404, {"error": "NOT_FOUND"})
                    return
                allowed = {"accepted", "edited", "rejected", "expert_review"}
                decision = payload.get("decision")
                if decision not in allowed:
                    self._json(400, {"error": "INVALID_REVIEW_DECISION"})
                    return
                result["review"] = {"decision": decision, "note": payload.get("note", "")[:1000]}
                self._json(200, result)
                return
            self._json(404, {"error": "NOT_FOUND"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": "INVALID_REQUEST", "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        """Use standard access logging while keeping document bodies out of logs."""
        # Do not place document text in access logs.
        super().log_message(format, *args)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("Request body too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    """Start the legacy local-only prototype server."""
    server = ThreadingHTTPServer(("127.0.0.1", 8080), PrototypeHandler)
    print("FinContract AI prototype: http://127.0.0.1:8080")
    server.serve_forever()


if __name__ == "__main__":
    main()
