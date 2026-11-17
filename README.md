# Self-Correction Evaluation Benchmarks

Measurement battery and analysis code for the paper's benchmark: can LLM
self-evaluation be trusted to filter incorrect self-generated code?

Five model families (GPT-5.4, DeepSeek-V4.1-Flash, GLM-5.3-Flash, Qwen-3.8-Flash,
GPT-6-Luna) each attempt 947 MBPP tasks at temperature 0; every candidate is
executed against the reference tests to fix ground truth, then judged by the
generator's own self-check and steelman prompts, by a neutral verifier, by three
repeated evaluation rounds, by an independently regenerated candidate, and by the
four other families in a crossed matrix. A 164-task HumanEval stratum (nine
incorrect candidates, two evaluators) supplies the clean paired demonstration.

## Reproduce the paper's numbers

Everything reported in the paper regenerates deterministically from the released
ledgers. Python 3.9+, stdlib only, except `scipy` (one script) and `openai`
(only if you also regenerate data, which is not required to reproduce any number).

```bash
python3 scripts/mbpp_v2_analysis.py                # main paired production analysis
python3 scripts/mbpp_v2_accounting.py              # fixed-denominator accounting + imputation bounds
python3 scripts/mbpp_v2_control_analysis.py        # neutral-verification control arm
python3 scripts/mbpp_v2_tier1_analysis.py          # repeated evaluation + candidate replication
python3 scripts/mbpp_v2_cross_analysis.py          # crossed-matrix discordance + bootstrap CIs
python3 scripts/mbpp_v2_crossed_model.py           # crossed evaluator x generator model
python3 scripts/mbpp_v2_moderator_analysis.py      # task-moderator (task-source) analysis
python3 scripts/mbpp_v2_error_severity_audit.py    # executes candidates vs reference asserts
python3 scripts/mbpp_v2_failure_types.py           # failure-type breakdown of incorrect candidates
python3 scripts/mbpp_v2_assert_visible_analysis.py # one-assert-visible Qwen control
python3 scripts/humaneval/paired_contrasts.py      # HumanEval paired contrasts
```

Bootstrap intervals are seeded (see the scripts); reruns are bit-identical.
Scripts overwrite the derived `analysis/` outputs they own, so run them in a
copy of the repo if you want to compare against the shipped outputs.

## Data layout

Each ledger is newline-delimited JSON. `events.jsonl` holds every provider call
with its full raw response, usage, finish reason, and prompt/response hashes.
Record files hold one row per (model, task) with ground truth, both arm verdicts,
and extraction status.

- `data/mbpp_v2/production/` — 4,735 pairs, both arms (9,470 evaluator arms)
- `data/mbpp_v2/control/` — neutral-verification control arm (4,718 records; 6,965 events, of which 2,241 are preserved HTTP 401 auth failures from a mid-run API-key invalidation on the GPT-5.4 arm; the 747 affected tasks were re-run after key replacement and all have valid final records)
- `data/mbpp_v2/repeated_eval/` — 3 repeated evaluation rounds (18,884 events)
- `data/mbpp_v2/replication/` — independently regenerated candidates
- `data/mbpp_v2/cross_eval/` — crossed evaluator x generator matrix (18,872 records; includes 210 preserved HTTP 401 events on the GPT-5.4 arm from the same key invalidation, all since re-run to valid final records)
- `data/mbpp_v2/assert_visible_qwen/` — Qwen control with one reference assert visible
- `data/mbpp_v2/pilot/` — pilot run
- `data/mbpp_v2/analysis/`, `tier1_analysis/`, `moderator_analysis/` — derived outputs
- `data/MBPP.jsonl`, `data/MBPP.corpus-provenance.json` — task corpus and provenance
- `data/humaneval/` — HumanEval stratum (data, responses, reproduction guide)

Ledger directories carry `manifest.sha256` over their raw files.

Reproducibility note: after an internal consistency audit, 35 cross-evaluation
cells were re-evaluated on the corrected candidates; all raw events, including
the superseded attempts, are released in the ledgers.

Ledger conventions: a (model, task) pair may appear more than once in
`events.jsonl` when an attempt was retried or regenerated. The canonical attempt
per pair is the one referenced by `derived_records.jsonl` (the authoritative
per-pair ledger; all verdicts and analyses key off it): normally the earliest
clean (`finish_reason=stop`, HTTP 200, no error) generation, with 39 pairs
referencing a later regenerated attempt (37 extracting to different code, 2
re-fetches carrying identical code). `candidate_records.jsonl` carries the same
canonical generation per pair.
Superseded attempts are preserved in `duplicate_records.jsonl`; every attempt
remains in `events.jsonl`. The canonical code is extracted from the referenced
generation event's raw response by `extract_code` (shipped in
`scripts/mbpp_v2_pilot.py`): the first fenced code block, then from the first
`def`/`import`/`from` line onward; if none exists, the task prompt is prepended.

Malformed or
incomplete records are kept in the ledgers and reported as counts; nothing is
silently dropped or imputed.

## Regenerating the data (optional)

`scripts/run_mbpp_v2_production.sh` and `scripts/mbpp_v2_pilot.py` perform the
provider calls with `OPENAI_API_KEY` (and provider base URLs) set; `scripts/validate_mbpp_v2_pilot.py`
checks pilot output structure. Generation takes days of API time and is not
needed for any analysis above.

## Citation

See the companion paper (IJCS submission). Family names in the ledgers
(`gpt-5.4`, `ds-v4-flash`, `glm-5.3-flash`, `qwen38-flash`, `gpt-6-luna`) map to
the paper's display names.
