.PHONY: setup-backend setup-frontend test-backend test-frontend frontend-check api-check e2e failure-e2e migrate retention run-worker run-backend run-frontend infra-check ingest-demo ingest-public evaluate-public verify-index compose-check compose-logs claude-check evaluate-expert-demo

PYTHON := backend/.venv/bin/python

setup-backend:
	/opt/homebrew/bin/python3.12 -m venv backend/.venv
	backend/.venv/bin/pip install -e 'backend[dev]'

setup-frontend:
	cd frontend && npm install

test-backend:
	cd backend && .venv/bin/python -m pytest

test-frontend:
	cd frontend && npm run lint && npm test && npm run build

frontend-check: test-frontend

api-check:
	cd backend && .venv/bin/pytest tests/test_documents_api.py tests/test_health.py

e2e: api-check

failure-e2e:
	cd backend && .venv/bin/python scripts/check_worker_failure.py

migrate:
	cd backend && .venv/bin/python scripts/migrate.py

retention:
	cd backend && .venv/bin/python scripts/enforce_retention.py

run-worker:
	cd backend && .venv/bin/python scripts/run_worker.py

run-backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && npm run dev

infra-check:
	cd backend && .venv/bin/python scripts/check_infrastructure.py

ingest-demo:
	cd backend && .venv/bin/python scripts/ingest_corpus.py ../research/demo_manifest.json ../research/demo_corpus/clause_patterns.jsonl

ingest-public:
	cd backend && .venv/bin/python scripts/ingest_corpus.py ../research/public_manifest_v0_1.json ../research/public_corpus/statutes.jsonl

evaluate-public:
	cd backend && .venv/bin/python scripts/evaluate_retrieval.py tests/fixtures/retrieval_eval_public_v0_1.jsonl --top-k 3 --min-hit-rate 1 --min-mrr 0.8

verify-index:
	cd backend && .venv/bin/python scripts/verify_index.py

compose-check:
	./scripts/check-compose.sh

compose-logs:
	docker compose logs --follow --tail=100 backend worker retention

claude-check:
	cd backend && PYTHONPATH=. .venv/bin/python scripts/check_anthropic.py

evaluate-expert-demo:
	cd backend && PYTHONPATH=. .venv/bin/python scripts/evaluate_experts.py tests/fixtures/expert_annotations_synthetic_v0_1.jsonl
