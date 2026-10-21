# Recommendation decision evaluation

Replays first-turn discovery requests (and short multi-turn conversations)
through the real prepared Store dialogue: `StoreConversation` → Expert decision
→ prepared presenter. Rasa is replaced by the intent named in each case, and no
language model is called. Candidate pools are E5 dense top-10 over prepared index
text, an approximation of hybrid retrieval; the decision stage, not retrieval,
is under test. Results are controlled engineering evidence against agent-authored
labels, not HEDGE-approved relevance labels, live Store quality or proposal KPIs.

| File | Purpose |
| --- | --- |
| `unseen.json` | 24 cases authored before the evidence matcher was calibrated. Its failures informed the first version's rules, so it is no longer a clean measure. |
| `unseen-2.json` | 20 cases authored after the rules were frozen; the generalization measure. |
| `conversations.json` | Five multi-turn scenarios; replies are judged by reading them. |
| `evaluate.py` | Runner and grader. |

Development data is `../retrieval/frozen.json` and `../retrieval/holdout.json`
against `../retrieval/catalogue.json`. Grades: **Pass** recommends only Apps
labelled complete or acceptable, including every complete App; **Partial** is
correct but misses a complete App; **Suggested** recommends nothing unsupported
and shows a complete App as its closest, explicitly unconfirmed statement;
**Fail(unsupported)** recommends a forbidden or unlabelled App;
**Fail(abstained)** shows no complete App. Partial fits may be explained, never
recommended.

Run with the pinned CPU E5 image described in [retrieval](../retrieval/README.md),
without a network, writing to a private directory outside Git:

```bash
docker run --rm --network none --memory 1100m --memory-swap 1100m --cpus 1 --user 1000:1000 \
  --tmpfs /tmp:rw,size=64m,mode=1777 -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/evidence" -w /repo \
  --entrypoint python "$RETRIEVAL_EVAL_IMAGE" evaluation/recommendation/evaluate.py \
  --queries evaluation/recommendation/unseen-2.json --output /evidence/unseen-2.json
```

`--conversations evaluation/recommendation/conversations.json` replays the
multi-turn scenarios. An authorized real Store observation can be passed with
`--catalogue` and its own query file; keep both outside Git. Results and design
decisions: [recommendation evidence](../../docs/t2-recommendation-evidence.md).
