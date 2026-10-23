"""Import explicitly source-reviewed bilingual preparation into a local Store projection.

The owned private file contains checksum-bound explanations and review provenance.
No upstream fetch, model request, source payload update or indexing is performed.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import time
from pathlib import Path

from hedge_shared import storage
from hedge_shared.store_knowledge import PREPARATION_VERSION, explanation, project

ROOT = Path(__file__).resolve().parents[1]


def prepare(store_id: str, reviewed: list[dict]) -> list[dict]:
    with storage.connection() as conn:
        rows = conn.execute(
            "SELECT id, checksum, payload, prepared_knowledge FROM catalog_apps "
            "WHERE source_store_id = %s AND active = true", (store_id,),
        ).fetchall()
    accepted = {record["id"]: record for record in reviewed}
    if (not accepted or len(accepted) != len(reviewed) or
            not set(accepted) <= {row["id"] for row in rows}):
        raise ValueError("Reviewed records must identify distinct current Apps in this Store")
    results = []
    for row in rows:
        if row["id"] not in accepted:
            continue
        app = project(row)
        record = accepted[row["id"]]
        review = record.get("review", {})
        knowledge = row["prepared_knowledge"]
        if (not app.get("active") or not app.get("visible")
                or not isinstance(knowledge, dict) or knowledge.get("checksum") != row["checksum"]
                or knowledge.get("version") != PREPARATION_VERSION
                or knowledge.get("projection", {}).get("id") != row["id"]):
            raise ValueError("Reconcile current visible Store preparation before importing prose")
        if (record.get("checksum") != row["checksum"] or
                review.get("method") not in ("human_source_review", "agent_source_review") or
                not review.get("reviewer") or not review.get("note")):
            raise ValueError("Source review must identify the current checksum, reviewer and rationale")
        prepared_prose = {**record["explanation"], "review": review}
        if not explanation({**app, "prepared_explanation": prepared_prose}):
            raise ValueError("Reviewed preparation is invalid or has unbound quotations")
        if knowledge.get("explanation") == prepared_prose:
            results.append({"status": "reused", "seconds": 0})
            continue
        start = time.monotonic()
        knowledge = {**knowledge, "explanation": prepared_prose}
        # A concurrent source update/withdrawal cannot publish stale prose.
        with storage.connection() as conn:
            changed = conn.execute(
                "UPDATE catalog_apps SET prepared_knowledge = %s::jsonb "
                "WHERE id = %s AND checksum = %s AND active = true "
                "AND prepared_knowledge->>'version' = %s",
                (json.dumps(knowledge), row["id"], row["checksum"], str(PREPARATION_VERSION)),
            ).rowcount
        if changed != 1:
            raise ValueError("Source changed during explanation preparation")
        results.append({"status": "source_review_import",
                        "seconds": round(time.monotonic() - start, 3)})
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--reviewed-file", type=Path, required=True)
    args = parser.parse_args()
    path = args.reviewed_file
    info = path.lstat()
    if (not path.is_absolute() or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid() or info.st_mode & 0o077
            or path.resolve().is_relative_to(ROOT)):
        parser.error("Use an owned mode-0600 regular file outside the repository")
    reviewed = json.loads(path.read_text())
    if not isinstance(reviewed, list) or not reviewed:
        parser.error("Reviewed preparation must be a nonempty record list")
    print(json.dumps(prepare(args.store_id, reviewed)))
