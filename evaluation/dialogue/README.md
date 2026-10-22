# Natural conversation evaluation

Multi-turn conversations in ordinary English, written to measure understanding
rather than to exercise particular rules. `run.py` replays them through the
dialogue of the repository mounted at `--repo`, so one runner and scorer measure
both a baseline commit and this branch. `score.py` applies implementation-
agnostic checks: expected subjects, source concepts, forbidden text, decision
outcomes, and generic failures that no answerable turn may show (a generic
clarification, "Which App do you mean?" for a named App, the open-question
fallback, or an unrequested recommendation verdict). Each turn's `act` label
records the intended interpretation for reading; it is not scored.

| Files | Status |
| --- | --- |
| `dev-real.json`, `dev-fictional.json`, `observed-real.json` | Development. May inform implementation. `observed-real` holds the owner's 22 October 8156 turns and the diagnosis probes. |
| `heldout-real.json`, `heldout-fictional.json` | **Sealed.** Run at milestones only; never tune rules, prompts or training data to their failures. |
| `final-real.json`, `final-unseen.json`, `catalogue-unseen.json` | **Sealed.** Run once at the end. `catalogue-unseen` holds Apps never seen during development. |

All sets were authored on 22 October 2026, before any implementation on
`feat/t2-conversational-architecture`, and committed first. SHA-256 at sealing:

```
f8f2b0f26723a7c5bdadd629107471d39ee8f2231beb38bd5945de8add4f546f  heldout-real.json
48630e173fd567f6e73249109b2b7a52096c4dc5f9314d354a80b7e0802322ce  heldout-fictional.json
13f71a196a5a73440a601087c799aefd453842f4cf843e55423784c6c1b3463c  final-real.json
b922d81ef5d5ad22a08cc102e5da09fb3c365f2e1c0e0fb0e094789c3fb2d06b  final-unseen.json
4f1a60e2d55acfbac95c19d892445aa9e2b89723fc88609c67f8514781a35192  catalogue-unseen.json
```

The author also wrote the implementation, so independence is procedural: sealed
sets are read only as totals during development, and training examples for
the interpreter are checked for overlap with sealed messages.

`private:real` sets need the authorized real Store observation via
`--catalogue` (kept outside Git). Run with the pinned E5 image, no network,
writing outside Git:

```bash
docker run --rm --network none --memory 1100m --cpus 1 --user 1000:1000 \
  --tmpfs /tmp:rw,size=64m,mode=1777 -e HOME=/tmp -e OMP_NUM_THREADS=1 \
  -v "$REPO:/repo:ro" -v "$PWD/evaluation/dialogue:/eval:ro" -v "$OUT:/out" -w /repo \
  --entrypoint python "$RETRIEVAL_EVAL_IMAGE" /eval/run.py --repo /repo \
  --scenarios /eval/dev-fictional.json --catalogue /repo/evaluation/retrieval/catalogue.json --output /out/dev.json
```

Without `--model-url` every model call fails immediately, as the 8156 planner
does when it times out. `--model-url` must point at an isolated model service
with a capacity plan, never at a deployed prototype's model.
