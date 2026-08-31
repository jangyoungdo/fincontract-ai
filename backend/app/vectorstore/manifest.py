from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def validate_manifest(manifest_path: Path, schema_path: Path) -> dict:
    """Require schema-valid, explicitly verified provenance before corpus ingestion."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest),
        key=lambda error: list(error.path),
    )
    if errors:
        formatted = "; ".join(f"{'.'.join(map(str, error.path))}: {error.message}" for error in errors)
        raise ValueError(f"Invalid research manifest: {formatted}")
    if manifest["status"] != "verified":
        raise ValueError("Research manifest must be verified before ingestion")
    return manifest
