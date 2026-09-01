import hashlib
import json
from pathlib import Path

from app.vectorstore.manifest import validate_manifest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = REPOSITORY_ROOT / "research" / "public_corpus" / "statutes.jsonl"
MANIFEST_PATH = REPOSITORY_ROOT / "research" / "public_manifest_v0_1.json"
SCHEMA_PATH = REPOSITORY_ROOT / "research" / "manifest.schema.json"


def test_public_corpus_manifest_and_hashes_are_reproducible() -> None:
    manifest = validate_manifest(MANIFEST_PATH, SCHEMA_PATH)
    records = [json.loads(line) for line in CORPUS_PATH.read_text(encoding="utf-8").splitlines()]
    dataset = manifest["datasets"][0]

    assert len(records) == dataset["accepted_count"] == 7
    assert dataset["redistribution_allowed"] is True
    assert dataset["license_basis_url"].startswith("https://www.law.go.kr/")
    assert dataset["content_hash"] == f"sha256:{hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest()}"
    for record in records:
        text_hash = hashlib.sha256(record["text"].encode()).hexdigest()
        assert record["source_hash"] == f"sha256:{text_hash}"
        assert record["authority"] == "국가법령정보센터"
        assert record["review_status"] == "verified"
