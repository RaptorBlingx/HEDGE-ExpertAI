.PHONY: build up down logs test lint seed pull-model health clean

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

# Run unit tests
test:
	cd shared && python -m pytest ../tests/unit/ -v

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
