# T2 functional core evaluation

`baseline-questions.json` reproduces reported failures plus the accepted fast path.
`heldout-questions.json` was frozen before running the new implementation. These
are agent-authored engineering scenarios, not HEDGE's jointly labelled pilot set.
`authored-catalogue.json` and `authored-queries.json` are a separate, explicitly
fictional catalogue with distractors, partial matches, restrictions, an unpublished
App and an injection attempt. Never import them into a real Store or mix them with
an authorized observation.

Capture complete actual widget transcripts against separately started real service
stacks (never the in-process workspace adapter):

```bash
WIDGET_BASE_URL=http://127.0.0.1:8106 \
PLAYWRIGHT_MODULE_PATH=/path/to/node_modules/playwright \
BROWSER_EXECUTABLE=/path/to/chromium \
node evaluation/t2/widget.cjs evaluation/t2/baseline-questions.json /private/output/after
```

The output parent must exist outside Git. The recorder retains rendered answers,
exact SSE messages/events, native identities, Rasa classification, semantic recovery
metadata, timings, browser errors and a screenshot. It writes each completed turn
immediately. Repeat against the unchanged baseline URL for before evidence; do not
substitute authored answers for actual widget responses.

Evaluate separately:

1. **Retrieval:** ranked candidates before suitability; recall@2/@5, precision,
   reciprocal rank, dense/lexical participation, and an AND-vs-OR lexical ablation.
2. **Recommendations:** the entire explicit request, including compound/numeric/
   negative requirements; false recommendations and missed relevant Apps.
3. **Evidence:** exact quotation integrity separately from semantic correctness.
   Code validates citations; independently read claims, qualifications, unknowns
   and each complete answer against the retained source. A model's own review is
   a guard, not human acceptance or a quality metric.
4. **Dialogue:** focused referents, subject changes, comparisons, no-match next
   steps and useful explanations; score whole sessions, not isolated keywords.
5. **Latency:** submit-to-complete widget timing; report prepared and model-assisted
   paths separately, plus inference prompt/output rates and resource limits.

Keep source observation time/checksums, model/runtime/embedding revisions, flags,
code SHA, raw failures and evaluator decisions with the private evidence. Two real
Apps cannot establish ranking quality at catalogue scale; authored-catalogue
results are engineering evidence only. Do not claim proposal KPIs from these runs.

## Current acceptance boundary

The [one-pass follow-up](../../docs/t2-efficient-interpretation.md) compares the
cached 2B text weights with `qwen3:4b-instruct-2507-q4_K_M` through actual service
boundaries. 4B is the better tested experimental candidate, with slower inference
and remaining false abstentions; neither establishes general English quality.
The ordinary path now uses one structured interpretation and source composition,
not generated prose/self-review. The multi-stage results below are historical.

The VM's cached 2B model was used for limited real-service integration. It is
not the quality target and has not established reliable source assessment. Do not
replace model-generated answers with hand-authored ones, remove failed runs, or
score mocked model contract tests as English recommendation success. The retained
baseline and limited-model transcripts include false abstentions and reviewer
failures. No stronger private endpoint is currently available.

On suitable inference infrastructure, replay the frozen held-out sessions and
independently assess all five dimensions above before enabling semantic recovery
on the existing private environment. The architecture supports model/context/output/
time budgets rather than requiring a particular CPU-bound model. Review context
packing for long metadata and more than two real Apps; missing complete descriptive
evidence deliberately prevents positive promotion. Rasa's observed confidence was
poorly calibrated on these natural requests; evaluate intent/entity calibration
separately from whether the expert can recover from a fallible hint.
