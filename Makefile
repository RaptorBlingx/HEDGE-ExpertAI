.PHONY: build up down logs test test-ci lint seed pull-model health clean openapi evaluate evaluate-search evaluate-chat evaluate-stream test-integration

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
	python -m pytest tests/unit/ -v --cov=hedge_shared --cov-report=term-missing

# Run unit tests with coverage enforcement (CI mode)
test-ci:
	python -m pytest tests/unit/ -v --cov=hedge_shared --cov-report=term-missing --cov-fail-under=80

# Lint with ruff
lint:
	ruff check shared/ services/ tests/

# Pull LLM model into Ollama
pull-model:
	docker compose exec ollama ollama pull qwen3.5:2b

# Seed mock data by triggering ingestion
seed:
	curl -s -X POST http://localhost:8004/api/v1/ingest/trigger | python -m json.tool

# Check health of all services
health:
	@echo "=== Gateway ===" && curl -sf http://localhost:8000/health || echo "DOWN"
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
	python3 evaluation/evaluate.py --mode all --total-apps 75

# Run evaluation — search mode only
evaluate-search:
	python3 evaluation/evaluate.py --mode search --total-apps 75

# Run evaluation — chat mode only
evaluate-chat:
	python3 evaluation/evaluate.py --mode chat --max-queries 10

# Run evaluation — stream mode only
evaluate-stream:
	python3 evaluation/evaluate.py --mode stream --max-queries 5

# Run integration tests (requires running services)
test-integration:
	python3 -m pytest tests/integration/ -v --tb=short
