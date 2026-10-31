---
name: p5-2-qa-runner
description: Step P5.2. Run the client QA checklist on the dev silver tables of one source with lib/qa_checks.py (row counts, schema vs STTM, PK unique, not-null, FK integrity, SCD2 validity, key patterns), combine results into sources/<id>/05_build/qa_results/summary.json, and explain each failure. Use after the P5.1 notebooks run in dev.
---

# P5.2 QA runner (phase P5, checkpoint CP5_code_qa)

## Steps
1. Run each notebook (or the dev Job). The last cell writes `05_build/qa_results/<table>.json` and calls `qa.combine_summaries(...)`, which writes `summary.json`.
2. Read `summary.json`. For each `fail` or `error`: check, table, metric, evidence, and cause:
   - code bug -> fix the TODO cell, run again;
   - STTM gap -> stop; raise feedback at `CP4_sttm`;
   - source data problem -> new question for the client; never hide it with a filter the STTM does not state.
3. Every applicable item in `standards/qa_checklist.md` must have a result for EVERY mapped table (`lib/qa_rules.py` says which items apply).
   A check that cannot run (for example QA-01 without `bronze_count`, QA-05 without `ENTITY_TABLES`) is `error`, not skipped.
   The CP5 gate compares `summary.json` with the STTM: a missing or non-passing check for any table blocks approval.
4. Feedback `data` items (for example "check these 20 legs"): run a targeted query, save it as `05_build/qa_results/fb_<FB-id>.json`, and report.
5. Log the run with `tools/x_feedback.py log`.

## Rules
- Never change a threshold, delete a check, or skip a table to pass.
- `error` is not `pass`.
- Dev only.

## Done when
All checks pass. Then `@p5-3-code-review` in a NEW chat.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p5-2-qa-runner --comment "..." --blocks CP5_code_qa`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
