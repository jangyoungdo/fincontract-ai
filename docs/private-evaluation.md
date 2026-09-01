# 비공개 문서 회귀 평가

계약서 원문과 기대표는 `private_eval/` 또는 저장소 밖의 암호화된 위치에만 둡니다. 이 경로는 Git에서 제외됩니다.

    backend/.venv/bin/python backend/scripts/evaluate_private_document.py /secure/contract.pdf /secure/expected-rules.json

기대표는 조문 라벨과 기대 규칙 ID만 담은 JSON 배열입니다. 명령은 원문을 출력하지 않고 파일 SHA-256, 규칙 버전, 조문별 기대/실제 ID와 pass/fail만 출력합니다.
