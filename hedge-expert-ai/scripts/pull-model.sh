#!/bin/bash
# Pull the LLM model into Ollama
set -e
echo "Pulling qwen3.5:2b model..."
docker compose exec ollama ollama pull qwen3.5:2b
echo "Model pulled successfully."
