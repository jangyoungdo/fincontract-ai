from app.evaluation.semantic import calibrate_threshold


def test_threshold_maximizes_f1_under_precision_floor_and_prefers_higher_tie() -> None:
    rows = [
        {"score": 0.91, "positive": True}, {"score": 0.86, "positive": True},
        {"score": 0.81, "positive": False}, {"score": 0.78, "positive": True},
        {"score": 0.4, "positive": False},
    ]
    assert calibrate_threshold(rows) == 0.78


def test_threshold_uses_documented_fallback_when_no_candidate_is_precise() -> None:
    assert calibrate_threshold([{"score": 0.8, "positive": False}]) == 0.72
