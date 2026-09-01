from pathlib import Path

import yaml

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def load_compose() -> dict:
    """Parse the deployment contract without requiring Docker on the test host."""
    return yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))


def test_compose_declares_complete_runtime_and_startup_gates() -> None:
    """Keep schema and corpus initialization ahead of long-running services."""
    services = load_compose()["services"]
    assert {
        "postgres",
        "redis",
        "chroma",
        "migrate",
        "corpus-init",
        "backend",
        "worker",
        "retention",
        "frontend",
    }.issubset(services)

    assert services["migrate"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["corpus-init"]["depends_on"]["chroma"]["condition"] == "service_healthy"
    for service_name in ("backend", "worker"):
        dependencies = services[service_name]["depends_on"]
        assert dependencies["migrate"]["condition"] == "service_completed_successfully"
        assert dependencies["corpus-init"]["condition"] == "service_completed_successfully"
        assert dependencies["redis"]["condition"] == "service_healthy"
    assert services["retention"]["depends_on"]["migrate"]["condition"] == (
        "service_completed_successfully"
    )


def test_compose_keeps_sensitive_state_out_of_source_bind_mounts() -> None:
    """Allow only reviewed public research data as a read-only host mount."""
    compose = load_compose()
    services = compose["services"]
    named_volumes = set(compose["volumes"])

    assert services["corpus-init"]["volumes"] == ["./research:/research:ro"]
    for service_name in ("backend", "worker", "retention"):
        for mount in services[service_name].get("volumes", []):
            source, _, _ = mount.partition(":")
            assert source in named_volumes

    for service_name in ("backend", "worker", "retention"):
        encryption_setting = services[service_name]["environment"]["DOCUMENT_ENCRYPTION_KEY"]
        assert encryption_setting == "${DOCUMENT_ENCRYPTION_KEY:?set DOCUMENT_ENCRYPTION_KEY}"


def test_compose_healthchecks_probe_real_service_endpoints() -> None:
    """Reject process-only checks that could mark unusable dependencies healthy."""
    services = load_compose()["services"]
    assert services["chroma"]["healthcheck"]["test"][-1].endswith("/api/v2/heartbeat")
    assert "/health/ready" in services["backend"]["healthcheck"]["test"][-1]
    assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
