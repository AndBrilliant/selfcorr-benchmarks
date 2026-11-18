#!/usr/bin/env python3
"""Batch-sensitivity bound for the same-family (diagonal) cross-evaluation contrast.

The diagonal cells of the cross-evaluation matrix come from the production ledger
(2026-11-05 03:03-12:01Z) and the off-diagonal cells from the cross-evaluation
ledger (2026-11-06/07), so the same-family indicator is collinear with a
run-batch factor. This script bounds how large that batch factor could be using
existing pinned data only: the repeated-evaluation ledger re-evaluates the same
frozen incorrect candidates with the same family in a separate run
(2026-11-05 13:25 - 2026-11-06 01:28Z). The run-to-run shift of the same-family
self-check false-acceptance rate is the observable signature of run-batch /
provider-side variation. Comparing the largest such shift per family against the
diagonal excess (production same-family minus cross off-diagonal) bounds the
fraction of the excess an adversarial batch attribution could account for.

Deterministic; stdlib only. Output: data/mbpp_v2/analysis/batch_sensitivity.json
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "mbpp_v2"


def main():
    # Production: T and self-check verdict per (model, task)
    prod = {}
    for line in open(DATA / "production" / "derived_records.jsonl"):
        r = json.loads(line)
        if r.get("T") is not None and r.get("selfcheck_verdict") in ("ACCEPT", "REJECT"):
            prod[(r["model"], r["task_id"])] = (r["T"], r["selfcheck_verdict"])

    # Same-family production self-check FA on incorrect candidates
    same_n, same_acc = defaultdict(int), defaultdict(int)
    for (m, _t), (T, v) in prod.items():
        if T == 0:
            same_n[m] += 1
            same_acc[m] += v == "ACCEPT"

    # Off-diagonal cross self-check FA on incorrect candidates (cross ledger, batch B)
    cross_n, cross_acc = defaultdict(int), defaultdict(int)
    for line in open(DATA / "cross_eval" / "cross_records.jsonl"):
        r = json.loads(line)
        key = (r["generator"], r["task_id"])
        if key not in prod or prod[key][0] != 0:
            continue
        if r["selfcheck_verdict"] not in ("ACCEPT", "REJECT"):
            continue
        cross_n[r["generator"]] += 1
        cross_acc[r["generator"]] += r["selfcheck_verdict"] == "ACCEPT"

    # Repeated same-family self-check verdicts (separate run) on the same frozen
    # incorrect candidates
    rep_n, rep_acc = defaultdict(int), defaultdict(int)
    for line in open(DATA / "repeated_eval" / "repeated_records.jsonl"):
        r = json.loads(line)
        key = (r["model"], r["task_id"])
        if key not in prod or prod[key][0] != 0:
            continue
        if r.get("selfcheck_r2_verdict") not in ("ACCEPT", "REJECT"):
            continue
        rep_n[r["model"]] += 1
        rep_acc[r["model"]] += r["selfcheck_r2_verdict"] == "ACCEPT"

    families = {}
    max_shift = 0.0
    min_excess = None
    for m in sorted(same_n):
        same_fa = 100.0 * same_acc[m] / same_n[m]
        cross_fa = 100.0 * cross_acc[m] / cross_n[m]
        rep_fa = 100.0 * rep_acc[m] / rep_n[m]
        excess = same_fa - cross_fa
        shift = rep_fa - same_fa
        max_shift = max(max_shift, abs(shift))
        min_excess = excess if min_excess is None else min(min_excess, excess)
        families[m] = {
            "same_family_production_fa_pct": round(same_fa, 2),
            "same_family_repeated_fa_pct": round(rep_fa, 2),
            "off_diagonal_cross_fa_pct": round(cross_fa, 2),
            "diagonal_excess_pct_points": round(excess, 2),
            "run_to_run_shift_pct_points": round(shift, 2),
            "n_incorrect": same_n[m],
        }

    result = {
        "schema": "mbpp-v2-batch-sensitivity/1",
        "batch_windows": {
            "production_evals": "2026-11-05T03:03Z..2026-11-05T12:01Z",
            "repeated_evals": "2026-11-05T13:25Z..2026-11-06T01:28Z",
            "cross_evals": "2026-11-06T06:10Z..2026-11-16T23:04Z",
        },
        "families": families,
        "summary": {
            "max_run_to_run_shift_pct_points": round(max_shift, 2),
            "min_diagonal_excess_pct_points": round(min_excess, 2),
            "max_fraction_of_excess_attributable_to_batch": round(
                max_shift / min_excess, 4
            ),
            "interpretation": (
                "Same-family self-check false acceptance on identical frozen "
                "incorrect candidates shifts by at most the stated run-to-run "
                "amount between two independent runs; attributing that entire "
                "shift to a run-batch factor bounds the batch share of the "
                "diagonal excess."
            ),
        },
    }
    out = DATA / "analysis" / "batch_sensitivity.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    for m, f in families.items():
        print(f"{m:20} excess={f['diagonal_excess_pct_points']:+.2f}  "
              f"shift={f['run_to_run_shift_pct_points']:+.2f}")
    return result


if __name__ == "__main__":
    main()
