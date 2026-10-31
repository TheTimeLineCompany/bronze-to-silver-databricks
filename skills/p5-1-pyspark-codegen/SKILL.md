---
name: p5-1-pyspark-codegen
description: Step P5.1. Turn an APPROVED sources/<id>/04_mapping/sttm.yaml into PySpark notebooks and a Job that follow the client naming, coding, and QA standards - generate the skeleton with a script, then complete only the TODO(genie) cells for dedup, joins, lookups, and derived columns. Use after handover H1 (CP4, and CP4b when needed, approved), and after CP5 feedback.
---

# P5.1 PySpark code generation (phase P5, checkpoint CP5_code_qa)

## Preconditions (check first; stop if one fails)
- `python tools/x_validate_gate.py --next <id>` shows the next checkpoint is `CP5_code_qa`.
- `04_mapping/sttm.yaml` has `status: approved`.
If not, tell the user which checkpoint is missing. Never code from a draft STTM.

## Inputs
- The approved STTM (the contract; do not change it here) and `04_mapping/exports/`.
- `standards/naming.yaml`, `standards/coding.md`, `standards/qa_checklist.md`.
- `lib/keys.py`, `lib/load_patterns.py`, `lib/qa_checks.py` (reuse; never re-implement).
- Open feedback in `05_build/feedback/CP5_code_qa/`.

## Steps
1. Generate: `python tools/p5_1_gen_notebook.py sources/<id>/04_mapping/sttm.yaml` -> `05_build/nb_slv_<id>_<table>.py` per table.
   Example output: `examples/generated_skeleton_example.py`.
   **Safe to run again** after an STTM change: it refreshes GENERATED cells and KEEPS your TODO(genie) code.
   - Run `--dry-run` first to see what will change.
   - A TODO cell whose specification changed gets a `# REVIEW(STTM changed)` block with the new spec. Update the code, then delete the REVIEW lines. CP5 is blocked while any REVIEW line remains.
   - A hand-edited GENERATED cell is replaced; the old file is kept as `.bak` and the run prints a warning.
   - Never use `--force` on a notebook with finished TODO work: it regenerates from scratch.
2. Keep every `# GENERATED` cell unchanged. Complete only `# TODO(genie)` cells:
   - **Dedup:** each `dedup` rule as a window function; set `bronze_count` after filter and dedup.
   - **Joins:** each STTM join. After an `N:1` join the row count must not change (assert).
   - **Lookups / FKs:** FKs with `fk.lookup_on` are GENERATED (cell `fk lookups`, `lib.keys.lookup_sk`): single or composite keys, current parent row, orphan policy (`unknown_member` -> `UNKNOWN_SK`; `reject` -> `<table>_quarantine` and `rejected_count`; `allow_null` -> NULL). Only FKs without `lookup_on` stay in the TODO cell; better: ask for `lookup_on` in the STTM (feedback at CP4).
   - **Same-source parents** (`fk.table`, e.g. line -> header): the parent notebook must run first in the job.
   - **Derived:** copy the exact STTM `transform`. Business-logic columns (BR id in the TODO line) must match `04_mapping/reviews/business_logic_signoff.md`.
   - **ENTITY_TABLES** is generated from `registry/entities.yaml`. An older notebook may still have a TODO `entities` cell, now marked `REVIEW(not in STTM)`: delete it.
   - **bronze_count:** set it in the dedup cell. Without it QA-01 reports `error` and CP5 fails.
   - SCD2 tables: set `effective_from` (the change timestamp) on every row. Late and out-of-order history is handled by `lib/load_patterns.scd2`; do not write SCD2 logic yourself.
3. Follow `standards/coding.md` (widgets for catalog and schema, no `collect()` on big data, no `print` logging, comment each rule).
4. **Shared masters** (`target_kind: master`): the notebook writes this source's STAGING table, not the master.
   Then run `python tools/p5_4_gen_master_build.py <Entity>` -> `masters/<master table>/nb_build_<master table>.py`.
   The build combines every source of the entity with the survivorship rules and seeds the unknown member.
   Complete its entities TODO cell. CP5 needs its QA (`masters/<table>/qa_results/summary.json`) complete and passing.
   Orphans with `orphan_policy: unknown_member` get `UNKNOWN_SK` (imported in the notebook); QA-05 fails if another policy uses it.
4b. The generated **publish metadata** cell writes table and column comments, tags (business object, data class, source),
   privacy tags and masks, and the informational PK/FK constraints to Unity Catalog (`lib/uc_publish.py`). It never fails the load;
   read its report. Do not remove it: Catalog Explorer, Genie spaces, and BI tools use this metadata.
5. Write the Job `05_build/job_slv_<id>.json` from `templates/job.json`: one task per notebook. Order: source notebooks of shared masters -> master builds -> process tables.
6. Feedback `code` items: apply the snippet in the named cell if it fits the STTM and standards; otherwise set the item `rejected` with a reason by a person, or raise a question.
7. Run in **dev only**. Then `@p5-2-qa-runner`.

## Rules
- If the STTM looks wrong, stop and raise feedback at CP4 (`x_feedback.py new <id> CP4_sttm ...`). Do not fix the mapping in code.
- Never write to prod schemas.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p5-1-pyspark-codegen --comment "..." --blocks CP5_code_qa`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
