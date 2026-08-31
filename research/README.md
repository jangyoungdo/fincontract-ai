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

## 현재 검증 코퍼스

`public_manifest_v0_1.json`과 `public_corpus/statutes.jsonl`에는 국가법령정보센터에서
확인한 「약관의 규제에 관한 법률」 7개 조문을 조문 단위로 담았습니다. 법령은
저작권법 제7조의 보호 대상 제외 정보이며, 출처 URL·본문 SHA-256·코퍼스 SHA-256을
함께 고정했습니다. 조문은 검색용으로 일부 열거를 축약했으므로 법률 판단에는 공식
원문을 다시 확인해야 합니다.

공정위 심결·표준약관·판례·분쟁사례는 개별 원문의 공개 범위와 재배포 조건을 확인하기
전까지 이 verified manifest에 넣지 않습니다. 아래 명령은 기본 로컬 해시 임베딩으로
적재하고 7개 개발 질의의 Hit@3과 MRR 기준을 검사합니다.

```bash
make ingest-public
make evaluate-public
```

`EMBEDDING_PROVIDER=chroma_default`는 Chroma에 포함된 로컬
`all-MiniLM-L6-v2`를 사용합니다. 최초 실행 때 약 80MB 모델을 내려받으며 외부 API로
계약 문장을 보내지 않습니다. 임베딩 차원이 다르므로 제공자를 바꿀 때는 별도의
`CHROMA_PATH`를 사용해야 합니다.
