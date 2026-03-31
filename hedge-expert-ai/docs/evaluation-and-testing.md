# Evaluation & Testing

Search quality evaluation framework, unit testing, and KPI measurement for HEDGE-ExpertAI.

---

## Table of Contents

- [KPI Targets](#kpi-targets)
- [Evaluation Framework](#evaluation-framework)
- [Test Queries](#test-queries)
- [Running Evaluations](#running-evaluations)
- [Understanding Metrics](#understanding-metrics)
- [Unit Tests](#unit-tests)
- [Integration Tests](#integration-tests)

---

## KPI Targets

| Metric | Target | Status |
|---|---|---|
| **Precision@2 (P@2)** | ≥ 70% | Primary relevance KPI |
| **Median Response Latency** | < 5 seconds | End-to-end from query to response |
| **Catalogue Freshness** | ≤ 24h update delay | Time from app publication to searchability |
| **Recall@5** | Tracked | Secondary quality indicator |
| **MRR** | Tracked | Mean Reciprocal Rank |

These KPIs are derived from the HEDGE-IoT Open Call Topic 15 requirements.

---

## Evaluation Framework

The evaluation script (`evaluation/evaluate.py`) automates search quality measurement against a labelled test set.

### What It Measures

1. **Precision@2 (P@2):** What fraction of the top 2 results are in the expected set?
2. **Recall@5 (R@5):** What fraction of expected apps appear in the top 5 results?
3. **Mean Reciprocal Rank (MRR):** How high does the first relevant result appear?
4. **Median Latency:** End-to-end search response time (50th percentile)
5. **P95 Latency:** Tail latency (95th percentile)

### How It Works

```
For each query in test_queries.json:
  1. POST /api/v1/apps/search with the query text
  2. Compare returned app IDs against expected_apps
  3. Compute P@2, R@5, and RR for that query
  4. Record latency
  5. Print per-query result: [OK] or [MISS]

After all queries:
  - Aggregate metrics (mean P@2, mean R@5, mean MRR, median latency)
  - Print summary
  - PASS if P@2 ≥ 70% AND median latency < 5s
```

---

## Test Queries

The test set (`evaluation/test_queries.json`) contains **50 labelled queries** covering all 8 SAREF categories.

### Format

```json
[
  {
    "query": "I need an app for monitoring energy consumption",
    "expected_apps": ["app-001", "app-038"],
    "saref_class": "Energy"
  }
]
```

| Field | Description |
|---|---|
| `query` | Natural language search query |
| `expected_apps` | List of app IDs that should appear in results |
| `saref_class` | Expected SAREF category for this query |

### Category Distribution

| SAREF Class | Query Count |
|---|---|
| Energy | 7 |
| Building | 6 |
| Environment | 5 |
| Agriculture | 6 |
| Water | 6 |
| City | 6 |
| Health | 6 |
| Manufacturing | 5 |
| **Total** | **50** (+ 1 general) |

### Query Patterns

The test set covers diverse query patterns:

- **Intent-based:** "I need an app for...", "Find me a..."
- **Task-based:** "Monitor energy consumption", "Detect water leaks"
- **Domain-specific:** "Precision irrigation for farming", "CNC tool wear prediction"
- **Descriptive:** "Smart building HVAC solution", "GPS tracking for livestock"

---

## Running Evaluations

### Prerequisites

All services must be running and the search index must be seeded:

```bash
make up
make seed
# Wait for services to stabilize
make health
```

### Run Evaluation

```bash
# Default: against localhost:8000
python evaluation/evaluate.py

# Custom API URL
python evaluation/evaluate.py --api-url http://your-server:8080

# Custom test queries
python evaluation/evaluate.py --queries path/to/queries.json
```

### Example Output

```
HEDGE-ExpertAI Evaluation
API: http://localhost:8000
Queries: evaluation/test_queries.json

Running 50 queries...

  [OK]   Q1: 'I need an app for monitoring energy consumption' → P@2=1.00 R@5=1.00 RR=1.00 (0.45s)
  [OK]   Q2: 'Find me a smart building HVAC solution' → P@2=0.50 R@5=1.00 RR=1.00 (0.38s)
  [MISS] Q3: 'Air quality monitoring for cities' → P@2=0.00 R@5=0.50 RR=0.33 (0.41s)
  ...

==================================================
RESULTS
==================================================
  Queries evaluated: 50/50
  Precision@2:      72.0%  (target: ≥70%)
  Recall@5:         85.0%
  MRR:              0.812
  Median latency:   0.42s  (target: <5s)
  P95 latency:      1.23s

  Overall: PASS ✓
```

---

## Understanding Metrics

### Precision@2 (P@2)

$$P@2 = \frac{|\text{top-2 results} \cap \text{expected apps}|}{2}$$

For each query, check if the top 2 returned apps are in the expected set. Target: ≥ 70% average across all queries.

### Recall@5 (R@5)

$$R@5 = \frac{|\text{top-5 results} \cap \text{expected apps}|}{|\text{expected apps}|}$$

Measures coverage: how many expected apps appear in top 5.

### Mean Reciprocal Rank (MRR)

$$MRR = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$

Where $\text{rank}_i$ is the position of the first relevant app in the results for query $i$.

### Score Composition

Each search result includes a breakdown:

```json
{
  "score": 0.8934,
  "vector_score": 0.9212,
  "keyword_score": 0.8500,
  "saref_boost": 1.0
}
```

Final score: $0.6 \times \text{vector} + 0.3 \times \text{keyword} + 0.1 \times \text{saref}$

---

## Unit Tests

### Running

```bash
# All unit tests
make test

# Or directly with pytest
cd shared && python -m pytest ../tests/unit/ -v

# Specific test file
cd shared && python -m pytest ../tests/unit/test_classifier.py -v
```

### Test Coverage

| Test File | Module | Tests |
|---|---|---|
| `test_classifier.py` | Chat Intent classifier | 7 parametrized test classes: greeting, help, search, detail, app ID extraction, unknown, long input |
| `test_prompts.py` | Expert Recommend prompts | System prompt, app context formatting, recommendation messages, explanation messages |
| `test_saref.py` | SAREF ontology mapping | All 8 classes (str + list), case insensitivity, empty input, no-match, query inference |
| `test_shared_models.py` | Shared Pydantic models | AppMetadata, SearchQuery, SearchResult, ChatRequest, HealthResponse, checksum computation |

### Test Patterns

Tests use `importlib` to load service modules directly without Docker, enabling fast local testing:

```python
_classifier_path = Path(__file__).parent.parent.parent / "services" / "chat-intent" / "app" / "classifier.py"
_spec = importlib.util.spec_from_file_location("chat_intent_classifier", _classifier_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
classify = _mod.classify
```

---

## Integration Tests

Integration tests (in `tests/integration/`) are designed to run against live Docker services:

```bash
# Start services first
make up && make seed

# Run integration tests (when available)
cd shared && python -m pytest ../tests/integration/ -v
```

### Manual Integration Testing

```bash
# Test chat flow
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Find apps for energy monitoring"}'

# Test direct search
curl -X POST http://localhost:8080/api/v1/apps/search \
  -H "Content-Type: application/json" \
  -d '{"query": "smart irrigation", "top_k": 3}'

# Test app detail
curl http://localhost:8080/api/v1/apps/app-001

# Test ingestion status
curl http://localhost:8080/api/v1/ingest/status

# Test health
curl http://localhost:8080/health
```

---

## Adding New Test Queries

To add new evaluation queries, edit `evaluation/test_queries.json`:

```json
{
  "query": "Your natural language query",
  "expected_apps": ["app-XXX", "app-YYY"],
  "saref_class": "Category"
}
```

Ensure:
- `expected_apps` are valid app IDs present in the seed data
- `saref_class` is one of the 8 supported classes
- Query text is realistic (how a user would actually ask)
