---
name: p2-1-doc-profiles
description: Step P2.1. Extract the client's already-profiled Excel workbooks (and Excel data dictionaries) for one source into one normalised table with confidence high, medium, low, or unknown, using a script instead of reading sheets. Use after CP1 is approved, or when a new profiling workbook arrives.
---

# P2.1 Client profiling extract (phase P2, checkpoint CP2_evidence)

## Goal
Turn many differently laid-out workbooks into ONE table you can filter. The script reads Excel; you read only the summary.

## Steps
1. Apply open feedback for `CP2_evidence` (for example a new header synonym, or a sheet to add to a `read_plan`).
2. Run `python tools/p2_1_extract_doc_profiles.py <id>` (one file: `--file IF-0004`).
   - The script reads only triaged `profiling_workbook` / `data_dictionary` Excel files that are core or supporting, and only the sheets in `read_plan.sheets`.
3. Read `02_evidence/profiling/doc_profiles_summary.md`.
   - Sheets "not extracted": add header synonyms in the script (by PR) or ask a person.
4. Use `02_evidence/profiling/doc_profiles.csv` by FILTER, not by reading it all:
   - key columns (`pk_candidate`), columns the brief names, and every `low` / `unknown` row.
5. Log the run with `tools/x_feedback.py log`.

## How confidence is normalised
| Raw value | Result |
|---|---|
| High, H, strong, confirmed, green, >= 80% (or >= 0.8) | high |
| Medium, Med, M, moderate, amber, yellow, 50-79% | medium |
| Low, L, weak, red, tentative, assumed, < 50% | low |
| empty or not clear | unknown (= treat as low) |

## Rules
- The client's confidence is a STARTING point. Bronze profiling (P2.2) decides structure.
- Do not copy rows into the evidence register here. That is P2.3, and only for columns that matter.

## Done when
`doc_profiles.csv` and `doc_profiles_summary.md` exist, and no needed sheet is unextracted.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p2-1-doc-profiles --comment "..." --blocks CP2_evidence`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
