"""Check that interpreter training examples do not copy sealed evaluation messages.

Compares each sealed message with every example (App names replaced by the
placeholder is not attempted: names in sealed sets are kept, so overlap is
measured on ordinary words). Reports exact copies and token-set Jaccard >= 0.8.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SEALED = ["heldout-real.json", "heldout-fictional.json", "final-real.json", "final-unseen.json"]


def tokens(text):
    return set(re.findall(r"[a-z0-9']+", text.casefold().replace("’", "'"))) - {"app"}


examples = [e for act in json.loads((HERE.parents[1] / "shared/hedge_shared/dialogue_acts.json").read_text())["acts"].values()
            for e in act["examples"]]
flagged = 0
for name in SEALED:
    for conversation in json.loads((HERE / name).read_text())["conversations"]:
        for turn in conversation["turns"]:
            m = tokens(turn["message"])
            best = max(examples, key=lambda e: len(m & tokens(e)) / max(1, len(m | tokens(e))))
            score = len(m & tokens(best)) / max(1, len(m | tokens(best)))
            if score >= .8:
                flagged += 1
                print(f"{name}: {turn['message']!r} ~ {best!r} ({score:.2f})")
print(f"{flagged} sealed messages closely match a training example")
sys.exit(1 if flagged else 0)
