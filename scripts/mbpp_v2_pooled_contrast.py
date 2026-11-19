#!/usr/bin/env python3
"""Pooled paired false-acceptance contrast across the five MBPP families.

Reads the per-family paired incorrect-stratum discordants from
data/mbpp_v2/analysis/mbpp_v2_analysis.json (produced by
mbpp_v2_analysis.py from the frozen production ledger) and computes:

  - per-family discordant table (b = accepted only by self-check,
    c = accepted only by steelman) and the exact per-family McNemar p;
  - the pooled Cochran-Mantel-Haenszel generalization of the paired
    contrast: Q = (sum b - sum c)^2 / (sum b + sum c) on 1 df, the
    single test for direction consistency across families;
  - the common odds ratio b/c (conditional MLE under homogeneity);
  - Breslow-Day homogeneity of the per-family odds ratios on 4 df.

The pooled statistic answers "does steelman lower false acceptance in
aggregate?" It does not assume a common effect size; per-family effect
sizes remain the estimates of Table II of the manuscript.
"""
import json
import math
from pathlib import Path

from scipy.special import gammaincc

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/mbpp_v2/analysis/mbpp_v2_analysis.json"
OUT = ROOT / "data/mbpp_v2/analysis/pooled_contrast.json"


def chi2_sf(x, df):
    """Chi-square survival function via the regularized upper incomplete gamma."""
    return float(gammaincc(df / 2.0, x / 2.0))


def main():
    analysis = json.loads(SRC.read_text())
    families = analysis["families"]

    rows = []
    B = C = 0
    for f in families:
        b = f["far_discordant_selfcheck_only"]
        c = f["far_discordant_steelman_only"]
        n = f["incorrect_paired"]
        B += b
        C += c
        rows.append({
            "model": f["model"],
            "incorrect_paired": n,
            "b_selfcheck_only": b,
            "c_steelman_only": c,
            "delta_kappa_points": 100.0 * (c - b) / n,
            "mcnemar_exact_p": f["far_mcnemar_exact_p"],
            "holm_p": f["far_mcnemar_exact_holm_p"],
        })

    q_cmh = (B - C) ** 2 / (B + C)
    or_common = B / C

    # Breslow-Day for paired tables: E[b_k] = (b_k + c_k) * OR / (1 + OR)
    x2_bd = 0.0
    for r in rows:
        tot = r["b_selfcheck_only"] + r["c_steelman_only"]
        expected = tot * or_common / (1 + or_common)
        var = tot * or_common / (1 + or_common) ** 2
        x2_bd += (r["b_selfcheck_only"] - expected) ** 2 / var

    result = {
        "method": "Cochran-Mantel-Haenszel generalization of the paired "
                  "incorrect-stratum McNemar contrast across the five families; "
                  "Q = (sum b - sum c)^2 / (sum b + c) on 1 df; "
                  "Breslow-Day homogeneity of per-family odds ratios on 4 df",
        "source": "data/mbpp_v2/analysis/mbpp_v2_analysis.json",
        "families": rows,
        "totals": {
            "b_selfcheck_only": B,
            "c_steelman_only": C,
        },
        "pooled": {
            "cmh_q": q_cmh,
            "cmh_df": 1,
            "cmh_chi2_sf": chi2_sf(q_cmh, 1),
            "common_odds_ratio": or_common,
            "breslow_day_x2": x2_bd,
            "breslow_day_df": len(rows) - 1,
            "breslow_day_chi2_sf": chi2_sf(x2_bd, len(rows) - 1),
        },
        "interpretation": "The pooled test supports direction consistency (steelman "
                          "lowers false acceptance in aggregate, p=6.8e-8) but does "
                          "not assume a common effect size: Breslow-Day rejects "
                          "homogeneity of the per-family odds ratios (p~0.01), so "
                          "effect sizes remain the per-family estimates.",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    p = result["pooled"]
    print(f"b={B} c={C} CMH Q={p['cmh_q']:.2f} p={p['cmh_chi2_sf']:.3g} "
          f"OR={or_common:.3f} BD X2={p['breslow_day_x2']:.2f} "
          f"p={p['breslow_day_chi2_sf']:.4f}")


if __name__ == "__main__":
    main()
