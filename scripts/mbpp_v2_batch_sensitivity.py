#!/usr/bin/env python3
"""Batch-sensitivity bound for the same-family (diagonal) cross-evaluation contrast.

The diagonal cells of the cross-evaluation matrix come from the production ledger
(2026-11-05) and the off-diagonal cells from the cross-evaluation ledger
(2026-11-06/07 plus a 140-record batch on 2026-11-16 covering GLM-, Qwen-, and
DeepSeek-generated candidates: 60, 60, and 20 records), so the same-family indicator is collinear with a
run-batch factor. This script bounds how large that batch factor could be using
existing pinned data only: the repeated-evaluation ledger re-evaluates the same
frozen incorrect candidates with the same family in separate runs (two retests,
both arms). The run-to-run shift of an arm's false-acceptance rate on identical
candidates is the observable signature of run-batch / provider-side variation.

All shifts are computed on MATCHED denominators: for every arm-by-repeat cell the
production rate is recomputed over exactly the candidates that have a usable
repeat verdict, so no shift is an artifact of unequal denominators. The bound
uses the largest |shift| across the twenty cells (two arms x two retests x five
families), which is the most conservative (largest) plausible batch component
under the transportability assumption stated in the manuscript: the
off-diagonal cross evaluations' batch shift is no larger in magnitude than the
largest observed same-family run-to-run shift, and not oppositely signed. No
cross-evaluation batch retest exists in these data to test that assumption.

Deterministic; stdlib only. Output: data/mbpp_v2/analysis/batch_sensitivity.json
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "mbpp_v2"
V = ("ACCEPT", "REJECT")

ARMS = [
    ("self-check", "selfcheck_verdict", "selfcheck_r2_verdict", "selfcheck_r3_verdict"),
    ("steelman", "steelman_verdict", "steelman_r2_verdict", "steelman_r3_verdict"),
]


def main():
    # Production: T and per-arm verdicts per (model, task)
    prod = {}
    for line in open(DATA / "production" / "derived_records.jsonl"):
        r = json.loads(line)
        if r.get("T") is not None:
            prod[(r["model"], r["task_id"])] = r

    # Off-diagonal cross self-check FA on incorrect candidates (cross ledger)
    cross_n, cross_acc = defaultdict(int), defaultdict(int)
    for line in open(DATA / "cross_eval" / "cross_records.jsonl"):
        r = json.loads(line)
        key = (r["generator"], r["task_id"])
        if key not in prod or prod[key].get("T") != 0:
            continue
        if r["selfcheck_verdict"] not in V:
            continue
        cross_n[r["generator"]] += 1
        cross_acc[r["generator"]] += r["selfcheck_verdict"] == "ACCEPT"

    # Matched run-to-run shifts: for each family, arm, and retest, recompute the
    # production rate over exactly the candidates with a usable repeat verdict.
    cells = []
    rep_rows = [json.loads(l) for l in open(DATA / "repeated_eval" / "repeated_records.jsonl")]
    for m in sorted({k[0] for k in prod}):
        for arm_name, prod_field, r2_field, r3_field in ARMS:
            for rep_name, rep_field in (("r2", r2_field), ("r3", r3_field)):
                pn = pa = rn = ra = 0
                for l in rep_rows:
                    if l["model"] != m:
                        continue
                    p = prod.get((m, l["task_id"]))
                    if not p or p.get("T") != 0:
                        continue
                    pv, rv = p.get(prod_field), l.get(rep_field)
                    if pv in V and rv in V:
                        pn += 1
                        pa += pv == "ACCEPT"
                        rn += 1
                        ra += rv == "ACCEPT"
                if pn < 50:
                    continue
                prod_fa = 100.0 * pa / pn
                rep_fa = 100.0 * ra / rn
                cells.append({
                    "family": m,
                    "arm": arm_name,
                    "repeat": rep_name,
                    "n_matched": pn,
                    "production_fa_pct": round(prod_fa, 3),
                    "repeat_fa_pct": round(rep_fa, 3),
                    "shift_pct_points": round(rep_fa - prod_fa, 3),
                    "abs_shift_pct_points": round(abs(rep_fa - prod_fa), 3),
                })

    # Diagonal excess per family (unchanged: production same-family vs cross
    # off-diagonal self-check FA on incorrect candidates)
    same_n, same_acc = defaultdict(int), defaultdict(int)
    for (m, _t), r in prod.items():
        if r.get("T") == 0 and r.get("selfcheck_verdict") in V:
            same_n[m] += 1
            same_acc[m] += r["selfcheck_verdict"] == "ACCEPT"

    families = {}
    min_excess = None
    for m in sorted(same_n):
        same_fa = 100.0 * same_acc[m] / same_n[m]
        cross_fa = 100.0 * cross_acc[m] / cross_n[m]
        excess = same_fa - cross_fa
        min_excess = excess if min_excess is None else min(min_excess, excess)
        families[m] = {
            "same_family_production_fa_pct": round(same_fa, 2),
            "off_diagonal_cross_fa_pct": round(cross_fa, 2),
            "diagonal_excess_pct_points": round(excess, 2),
            "n_incorrect": same_n[m],
        }

    max_shift = max(c["abs_shift_pct_points"] for c in cells)
    result = {
        "schema": "mbpp-v2-batch-sensitivity/2",
        "batch_windows": {
            "production_evals": "2026-11-05T03:03Z..2026-11-05T12:01Z",
            "repeated_evals": "2026-11-05T13:25Z..2026-11-06T01:28Z",
            "cross_evals": "2026-11-06T06:10Z..2026-11-16T23:04Z",
            "note": "cross ledger spans 2026-11-06/07 plus a 140-record batch on "
                    "2026-11-16 (60 GLM-, 60 Qwen-, and 20 DeepSeek-generated "
                    "candidates)",
        },
        "families": families,
        "matched_run_to_run_cells": cells,
        "summary": {
            "max_abs_run_to_run_shift_pct_points": round(max_shift, 2),
            "min_diagonal_excess_pct_points": round(min_excess, 2),
            "max_fraction_of_excess_attributable_to_batch": round(
                max_shift / min_excess, 4
            ),
            "interpretation": (
                "All shifts are computed on matched denominators (identical "
                "candidate sets per cell). The largest observed run-to-run shift "
                "across the twenty arm-by-repeat cells bounds the largest "
                "plausible batch component of the diagonal excess UNDER the "
                "transportability assumption stated in the manuscript: the "
                "off-diagonal (cross-evaluation) cells' batch shift is no larger "
                "in magnitude than the largest observed same-family run-to-run "
                "shift, and not oppositely signed. That assumption is untestable "
                "from these data (no cross-evaluation batch retest exists). "
                "Under it, batch could account for up to the stated fraction of "
                "the smallest diagonal excess; equivalently the family component "
                "is at least the remainder. This bound is weaker than the "
                "previous schema/1 value (24%), which used self-check R2 only on "
                "unequal denominators and understated observed run-to-run "
                "variability."
            ),
        },
    }
    out = DATA / "analysis" / "batch_sensitivity.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    worst = max(cells, key=lambda c: c["abs_shift_pct_points"])
    print(f"worst cell: {worst['family']} {worst['arm']} {worst['repeat']} "
          f"{worst['shift_pct_points']:+.2f}pp (n={worst['n_matched']})")
    return result


if __name__ == "__main__":
    main()
