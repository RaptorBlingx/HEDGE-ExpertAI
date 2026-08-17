.PHONY: build up down logs test test-ci lint frontend-test seed pull-model health clean openapi evaluate evaluate-search evaluate-chat evaluate-stream test-integration migrate e2e backup restore-drill

# Build all Docker images
build:
	docker compose build

# Start all services
up:
	docker compose up -d

# Stop all services
down:
	docker compose down

# View logs (follow)
logs:
	docker compose logs -f

# Run unit tests with coverage
test:
	python3 -m pytest tests/unit/ -v --cov=shared/hedge_shared --cov-branch --cov-report=term-missing

# Run unit tests with coverage enforcement (CI mode)
test-ci:
	python3 -m pytest tests/unit/ -v --cov=shared/hedge_shared --cov-branch --cov-report=term-missing --cov-fail-under=80

# Lint with ruff
lint:
	ruff check shared/ services/ tests/ scripts/ evaluation/

# Run pinned frontend component tests
frontend-test:
	cd frontend && npm ci && npm test

# Apply ordered PostgreSQL migrations under an advisory lock
migrate:
	docker compose run --rm migrations

# Run the deterministic live-stack acceptance profile
e2e:
	docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build \
		postgres valkey-cache valkey-queue qdrant mock-api discovery-ranking \
		metadata-ingest metadata-worker metadata-scheduler expert-recommend \
		rasa chat-intent gateway
	./scripts/e2e_smoke.sh

# Create an encrypted PostgreSQL/Qdrant/Valkey backup
backup:
	./scripts/backup.sh

# Restore a backup into disposable isolated containers (BACKUP_SET=/absolute/path)
restore-drill:
	test -n "$(BACKUP_SET)"
	./scripts/restore_drill.sh "$(BACKUP_SET)"

# Pull LLM model into Ollama
pull-model:
	docker compose exec ollama ollama pull qwen3.5:2b

# Seed mock data by triggering ingestion
seed:
	curl -s -X POST http://localhost:8004/api/v2/ingestion/runs | python3 -m json.tool

# Check health of all services
health:
	@echo "=== Gateway ===" && curl -sf http://$$(docker compose port gateway 8000)/health || echo "DOWN"
	@echo "=== Chat-Intent ===" && curl -sf http://localhost:8001/health || echo "DOWN"
	@echo "=== Expert-Recommend ===" && curl -sf http://localhost:8002/health || echo "DOWN"
	@echo "=== Discovery-Ranking ===" && curl -sf http://localhost:8003/health || echo "DOWN"
	@echo "=== Metadata-Ingest ===" && curl -sf http://localhost:8004/health || echo "DOWN"
	@echo "=== Mock-API ===" && curl -sf http://localhost:9000/health || echo "DOWN"

# Remove all containers, volumes, and images
clean:
	docker compose down -v --rmi local

# Export OpenAPI specs from all services
openapi:
	python3 scripts/export_openapi.py

# Run evaluation suite — all modes
evaluate:
	python3 evaluation/evaluate.py --mode all --total-apps 120

# Run evaluation — search mode only
evaluate-search:
	python3 evaluation/evaluate.py --mode search --total-apps 120

# Run evaluation — chat mode only
evaluate-chat:
	python3 evaluation/evaluate.py --mode chat --max-queries 10

# Run evaluation — stream mode only
evaluate-stream:
	python3 evaluation/evaluate.py --mode stream --max-queries 5

# Run integration tests (requires running services)
test-integration:
	python3 -m pytest tests/integration/ -v --tb=short
