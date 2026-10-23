# Conversation evaluation (21 October round)

Scenario sets from the previous conversational round. Their runner was removed with
the dialogue it drove; replay them with [the natural conversation runner](../dialogue/README.md)
(one catalogue per run: `development.json` mixes real-catalogue R* and fictional F* cases).

| File | Purpose |
| --- | --- |
| `development.json` | R*: replays of the observed 8156 conversations (needs an authorized real Store observation via `--catalogue`, kept outside Git); F*: fictional catalogue. |
| `heldout.json` | Authored before that round's act grammar; not tuned. |
| `heldout-2.json` | Authored after reading held-out run 1; later informed two grammar fixes. |
| `live.json` | Model-dependent turns. |
