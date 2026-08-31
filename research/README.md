# 리서치 코퍼스 준비 영역

이 디렉터리에는 사용자 계약서가 아니라 공개·허가된 법률 리서치 자료만 둡니다.

## 디렉터리

- `statutes/`: 법률, 시행령, 공식 지침
- `decisions/`: 공정거래위원회 심결·시정 사례
- `court_decisions/`: 공개·재배포 가능한 판례·판결 자료
- `disputes/`: 분쟁조정 사례
- `clause_patterns/`: 검증된 위험·비위험 조항 예시
- `rules/`: 규칙의 조사 근거와 검토 기록

## 적재 게이트

1. 출처 URL과 수집일 확인
2. 원본 hash 생성
3. 라이선스와 재배포 가능 여부 확인
4. 포함·제외 기준 적용
5. 중복 제거
6. 평가 데이터 중복 여부 확인
7. manifest schema 검증
8. ChromaDB 인덱싱

원본 자료가 확보되기 전에는 `research_manifest.example.json`을 실제 manifest로 간주하지 않습니다.

