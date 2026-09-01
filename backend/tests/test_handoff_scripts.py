import shutil
import stat
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_prepare_local_env_generates_hidden_secrets_without_overwrite(tmp_path: Path) -> None:
    """Protect the collaborator's local secrets and make setup idempotent."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script = scripts_dir / "prepare-local-env.sh"
    shutil.copy2(REPOSITORY_ROOT / "scripts/prepare-local-env.sh", script)
    shutil.copy2(REPOSITORY_ROOT / ".env.example", tmp_path / ".env.example")

    first = subprocess.run([str(script)], check=True, capture_output=True, text=True)
    env_file = tmp_path / ".env"
    first_contents = env_file.read_text(encoding="utf-8")

    assert "created .env" in first.stdout
    assert "replace-with-a-generated-fernet-key" not in first_contents
    assert "replace-with-a-long-random-admin-token" not in first_contents
    assert "ANTHROPIC_API_KEY=\n" in first_contents
    assert "LLM_PROVIDER=fake" in first_contents
    assert "ALLOW_EXTERNAL_LLM=false" in first_contents
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    for line in first_contents.splitlines():
        if line.startswith(("DOCUMENT_ENCRYPTION_KEY=", "ADMIN_AUDIT_TOKEN=")):
            assert line.partition("=")[2] not in first.stdout

    second = subprocess.run([str(script)], check=True, capture_output=True, text=True)
    assert "leaving it unchanged" in second.stdout
    assert env_file.read_text(encoding="utf-8") == first_contents


def test_handoff_scripts_are_executable() -> None:
    """Keep every documented checkpoint directly runnable after checkout."""
    for name in (
        "prepare-local-env.sh",
        "check-wsl-environment.sh",
        "check-compose-prereqs.sh",
        "run-baseline.sh",
        "collect-diagnostics.sh",
    ):
        mode = (REPOSITORY_ROOT / "scripts" / name).stat().st_mode
        assert mode & stat.S_IXUSR
