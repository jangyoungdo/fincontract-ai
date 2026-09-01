#!/usr/bin/env python3
"""Smoke-test the complete document lifecycle through the Next.js proxy only."""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
import uuid
from pathlib import Path


FRONTEND_SMOKE_ADDRESS = os.getenv("FRONTEND_SMOKE_ADDRESS", "127.0.0.1:3000")
FRONTEND_SMOKE_HOST, FRONTEND_SMOKE_PORT_TEXT = FRONTEND_SMOKE_ADDRESS.rsplit(":", 1)
FRONTEND_SMOKE_PORT = int(FRONTEND_SMOKE_PORT_TEXT)


def request(method: str, path: str, *, body: bytes | None = None, headers: dict[str, str] | None = None, host: str = "127.0.0.1:3000") -> tuple[int, dict[str, str], bytes]:
    """Call the frontend port while varying only the public Host header."""
    connection = http.client.HTTPConnection(
        FRONTEND_SMOKE_HOST,
        FRONTEND_SMOKE_PORT,
        timeout=20,
    )
    request_headers = {"Host": host, **(headers or {})}
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    payload = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    connection.close()
    return response.status, response_headers, payload


def expect_json(method: str, path: str, *, expected: tuple[int, ...], body: bytes | None = None, headers: dict[str, str] | None = None, host: str) -> dict:
    status, _, payload = request(method, path, body=body, headers=headers, host=host)
    if status not in expected:
        raise RuntimeError(f"{method} {path} returned HTTP {status}")
    return json.loads(payload)


def main() -> int:
    fixture = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1] / "backend/tests/fixtures/e2e-contract.txt"
    )
    content = fixture.read_bytes()
    boundary = f"fincontract-{uuid.uuid4().hex}"
    multipart = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="e2e-contract.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()

    # These hosts exercise the same-origin design used by localhost, direct IP,
    # LAN aliases, and preview/tunnel domains without contacting backend port 8000.
    host_headers = ["localhost:3000", "127.0.0.1:3000", "fincontract.lan:3000", "preview.example.invalid"]
    for host in host_headers:
        status, _, _ = request("GET", "/", host=host)
        if status != 200:
            raise RuntimeError(f"frontend rejected Host {host!r} with HTTP {status}")

    document_id = ""
    try:
        uploaded = expect_json(
            "POST",
            "/api/v1/documents",
            expected=(201,),
            body=multipart,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            host=host_headers[2],
        )
        document_id = uploaded["id"]
        created = expect_json(
            "POST",
            f"/api/v1/documents/{document_id}/analyses",
            expected=(201, 202),
            body=json.dumps({"experiment_arm": "A"}).encode(),
            headers={"Content-Type": "application/json"},
            host=host_headers[3],
        )
        analysis_id = created["id"]
        current = created
        for _ in range(120):
            if current["status"] in {"completed", "failed"}:
                break
            time.sleep(1)
            current = expect_json(
                "GET",
                f"/api/v1/analyses/{analysis_id}",
                expected=(200,),
                host=host_headers[1],
            )
        if current["status"] != "completed":
            raise RuntimeError(f"analysis ended with status {current['status']} and code {current.get('error_code')}")

        status, headers, pdf = request(
            "GET",
            f"/api/v1/analyses/{analysis_id}/report.pdf",
            host=host_headers[0],
        )
        if status != 200 or headers.get("content-type") != "application/pdf" or not pdf.startswith(b"%PDF-"):
            raise RuntimeError("frontend proxy did not return a valid PDF report")
        print(f"[proxy] lifecycle passed for document {document_id} and analysis {analysis_id}")
        return 0
    finally:
        if document_id:
            status, _, _ = request("DELETE", f"/api/v1/documents/{document_id}", host=host_headers[1])
            if status not in {200, 404}:
                print(f"[proxy] cleanup returned HTTP {status}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
