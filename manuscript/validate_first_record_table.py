#!/usr/bin/env python3
"""Validate manuscript first-record rows against the public archived JSON.

Usage: python3 validate_first_record_table.py /path/to/first_record_sensitivity.json
No model calls or statistical recomputation are performed.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTRASTS = (
    "steelman_minus_selfcheck",
    "control_minus_selfcheck",
    "steelman_minus_control",
)
MODEL_BY_PREFIX = {
    "DeepSeek": "DeepSeek-V4.1-Flash",
    "GLM": "GLM-5.3-Flash",
    "Qwen": "Qwen-3.8-Flash",
    "GPT-5.4": "GPT-5.4",
    "GPT-6-Luna": "GPT-6-Luna",
}


def number(text: str) -> float:
    text = text.strip().strip("$").strip("\\()")
    # Handle LaTeX scientific notation without depending on a TeX renderer.
    match = re.fullmatch(r"([0-9.]+)\\times10\^\{(-?\d+)\}", text)
    if match:
        return float(match.group(1)) * 10 ** int(match.group(2))
    return float(text)


def expected_rows(archive: dict) -> dict[tuple[str, str], tuple]:
    result = {}
    for family in archive["families"]:
        for cohort in ("failure_as_rejection", "all_first_success"):
            analysis = family[cohort]
            t0 = analysis["acceptance_counts"]["T0"]
            p_values = tuple(
                analysis["comparisons"][name]["mcnemar_p_holm"] for name in CONTRASTS
            )
            result[(family["model"], cohort)] = (
                analysis["n"], t0["n"], t0["sc"], t0["st"], t0["control"], *p_values
            )
    return result


def check_row(label: str, fields: list[str], expected: tuple, errors: list[str]) -> None:
    if len(fields) != 8:
        errors.append(f"{label}: expected 8 fields, found {len(fields)}")
        return
    counts = tuple(int(value) for value in fields[:5])
    if counts != expected[:5]:
        errors.append(f"{label}: counts {counts} != archived {expected[:5]}")
    for index, (printed, archived) in enumerate(zip(fields[5:], expected[5:]), 1):
        displayed = number(printed)
        rounded = float(f"{archived:.3g}")
        if not math.isclose(displayed, rounded, rel_tol=1e-12, abs_tol=0.0):
            errors.append(
                f"{label}: Holm p{index} {displayed:.12g} != archived {archived:.12g} "
                f"(three-significant-digit form {rounded:.12g})"
            )


def validate_tex(text: str, expected: dict, errors: list[str]) -> int:
    block = text.split(r"\label{tab:first_record}", 1)[1].split(r"\end{table*}", 1)[0]
    cohort = None
    checked = 0
    for line in block.splitlines():
        if "Fixed-947 failure-as-rejection" in line:
            cohort = "failure_as_rejection"
        elif "All-three-first-records-successful" in line:
            cohort = "all_first_success"
        elif "&" in line and line.rstrip().endswith(r"\\"):
            fields = [field.strip() for field in line.rstrip()[:-2].split("&")]
            model = fields[0]
            if model not in {family for family, _ in expected}:
                continue
            check_row(f"main.tex {model}/{cohort}", fields[1:], expected[(model, cohort)], errors)
            checked += 1
    return checked


def validate_response(text: str, expected: dict, errors: list[str]) -> int:
    checked = 0
    for line in text.splitlines():
        if not line.startswith("| ") or line.count("|") != 10:
            continue
        fields = [field.strip() for field in line.strip("|").split("|")]
        cohort_and_model = fields[0]
        if cohort_and_model.startswith("FAR "):
            cohort = "failure_as_rejection"
            prefix = cohort_and_model[4:]
        elif cohort_and_model.startswith("Successful-first "):
            cohort = "all_first_success"
            prefix = cohort_and_model[17:]
        else:
            continue
        model = MODEL_BY_PREFIX[prefix]
        check_row(
            f"REVIEW_RESPONSE.md {model}/{cohort}", fields[1:], expected[(model, cohort)], errors
        )
        checked += 1
    return checked


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    archive = json.loads(Path(sys.argv[1]).read_text())
    expected = expected_rows(archive)
    errors: list[str] = []
    checked = validate_tex((ROOT / "main.tex").read_text(), expected, errors)
    checked += validate_response((ROOT / "REVIEW_RESPONSE.md").read_text(), expected, errors)
    if checked != 20:
        errors.append(f"Expected 20 manuscript/response rows, checked {checked}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Validated {checked} first-record rows against {sys.argv[1]}")


if __name__ == "__main__":
    main()
