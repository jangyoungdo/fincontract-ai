import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DATASET = BACKEND_ROOT / "tests/fixtures/loan_terms_synthetic_v0_1.jsonl"
SCRIPT = BACKEND_ROOT / "scripts/evaluate_rule_baseline.py"


def test_baseline_emits_reproducibility_metadata_without_case_text() -> None:
    """Keep local experiment artifacts comparable without copying contracts."""
    environment = {
        **os.environ,
        "LLM_PROVIDER": "fake",
        "FINCONTRACT_RUN_ID": "baseline-test",
        "FINCONTRACT_CODE_COMMIT": "a" * 40,
        "FINCONTRACT_CODE_DIRTY": "false",
        "FINCONTRACT_IMAGE_ID": "sha256:test",
        "FINCONTRACT_CONTAINER_ARCHITECTURE": "amd64",
        "FINCONTRACT_PLATFORM": "windows-wsl2-x86_64",
    }
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(DATASET)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    result = json.loads(completed.stdout)

    assert result["run_id"] == "baseline-test"
    assert result["provider"] == "fake"
    assert result["code_commit"] == "a" * 40
    assert result["code_dirty"] is False
    assert result["container_image_id"] == "sha256:test"
    assert result["container_architecture"] == "amd64"
    assert result["platform"] == "windows-wsl2-x86_64"
    assert result["dataset_sha256"] == hashlib.sha256(DATASET.read_bytes()).hexdigest()
    assert result["dataset_is_synthetic"] is True
    assert result["case_count"] == 12
    assert all("text" not in case for case in result["cases"])
