# Conversation evaluation

Replays multi-turn conversations through the repository's own dialogue: chat
routing (regex NLU unless `RASA_ENABLED`), `StoreConversation`, Expert decisions,
presenter and explainer. HTTP hops are local calls; candidate pools are E5 dense
top-10 as in [recommendation](../recommendation/README.md). Without `--model-url`
no language model is called and model-assisted acts take their prepared fallback.

| File | Purpose |
| --- | --- |
| `development.json` | R*: replays of the observed 8156 conversations (needs an authorized real Store observation via `--catalogue`, kept outside Git); F*: fictional catalogue. May inform implementation. |
| `heldout.json` | Authored before the conversation-act implementation; never tuned. |
| `heldout-2.json` | Authored after reading held-out run 1, before its fixes; later informed two grammar fixes. |
| `run.py` | Runner; writes JSON and a readable Markdown transcript. |

Checks per turn are coarse signals (subject retained, any expected concept,
forbidden phrases, decision outcome, model use, 5-gram repetition of an earlier
answer). Read the transcript; do not tune rules to individual held-out sentences.

Run with the pinned CPU E5 image, without a network, writing outside Git:

```bash
docker run --rm --network none --memory 1100m --memory-swap 1100m --cpus 1 --user 1000:1000 \
  --tmpfs /tmp:rw,size=64m,mode=1777 -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$PWD:/repo:ro" -v "$EVIDENCE_DIR:/evidence" -w /repo \
  --entrypoint python "$RETRIEVAL_EVAL_IMAGE" evaluation/conversation/run.py \
  --scenarios evaluation/conversation/heldout.json --output /evidence/heldout.json
```

`--model-url` points explanation and interpretation calls at an Ollama endpoint.
Use it only for an isolated, verified model service with an explicit capacity
plan; it must not compete with a deployed prototype's model. Results and design:
[conversational experience](../../docs/t2-conversational-experience.md).
