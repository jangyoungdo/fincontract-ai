from app.services.analysis_jobs import QUEUE_NAME, enqueue_analysis, get_progress, progress_key, set_progress


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.queues: dict[str, list[str]] = {}

    def set(self, key: str, value: str, ex: int) -> None:
        assert ex > 0
        self.values[key] = value

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def rpush(self, key: str, value: str) -> None:
        self.queues.setdefault(key, []).append(value)


def test_progress_state_is_non_sensitive_and_enqueue_uses_only_analysis_id() -> None:
    redis_client = FakeRedis()
    set_progress(redis_client, "analysis-123", "analyzing", 25)
    assert get_progress(redis_client, "analysis-123")["percent"] == 25
    assert progress_key("analysis-123") in redis_client.values

    enqueue_analysis(redis_client, "analysis-123")
    assert redis_client.queues[QUEUE_NAME] == ["analysis-123"]
    assert "document" not in redis_client.queues[QUEUE_NAME][0]
