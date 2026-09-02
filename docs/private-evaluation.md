# 비공개 문서 회귀 평가

계약서 원문과 기대표는 `private_eval/` 또는 저장소 밖의 암호화된 위치에만 둡니다. 이 경로는 Git에서 제외됩니다.

    backend/.venv/bin/python backend/scripts/evaluate_private_document.py /secure/contract.pdf /secure/expected-rules.json --mode full

운영 제품은 단일 `full_pipeline`만 제공합니다. `rules-only`는 제품 모드가 아니라 회귀 기준선이며 위 명령의 `--mode rules-only`로만 실행합니다. 기대표 `mvp-ground-truth-v0.4.0`은 `sections[]`에 `section_id`, `required_rule_ids`, `allowed_rule_ids`, `forbidden_rule_ids`, `expected_candidate_categories`, 필요 시 `allowed_candidate_categories`를 기록합니다. 이전 조문 라벨·`expected_rule_ids` 배열도 읽을 수 있습니다. 명령은 원문을 출력하지 않고 파일 SHA-256, 규칙·의미 모델 버전, 규칙·후보·통합 precision/recall/F1, 규칙·후보 유형별 지표, 정상 조항 오탐 수, 내부 RAG 제거·근거 부족 수, 동일 조항에서 결정론 규칙과 의미 후보가 같은 규칙을 중복 지목한 비율, 조문별 pass/fail만 출력합니다. `--openai-context`는 마스킹된 분석 조항을 외부로 보내는 명시적 평가 옵션입니다.

비공개 6개 문서는 임계값 조정에 사용하지 않습니다. 합성 개발셋으로 임계값을 고정한 다음 `rules-only ≥ 75%`, `full ≥ 85%`, full의 규칙 탐지 보존, 전문·별지 오탐 0건을 승인 조건으로 확인합니다.
