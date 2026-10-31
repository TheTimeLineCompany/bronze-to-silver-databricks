---
name: p4-1-sttm-author
description: Step P4.1. Write or update the source-to-target mapping sources/<id>/04_mapping/sttm.yaml for one source - target tables with business object, data class, grain, load pattern, keys, joins, FKs to shared masters, column transformations, business rules, and evidence ids for every column. Use after CP2, CP3, and CP3b are approved, and after CP4 or CP4b feedback.
---

# P4.1 STTM author (phase P4, checkpoints CP4_sttm and CP4b_business_logic)

## Goal
A complete mapping that phase 2 can turn into code without questions, and where every column traces back to a business object and to evidence.

## Inputs (read only these)
- `01_intake/source_brief.md`, `02_evidence/evidence_register.csv`
- `02_evidence/discovery/summary.md`, `tables.csv` (role, grain key, business object, `scope`), `links.csv` (FKs, notes on key rules),
  `column_scope.csv` (column class and scope: logs, audit, secrets, personal data)
- Active instructions for `p4-1-sttm-author` or `all` in `sources/<id>/instructions.yaml`, and `<phase>/handover/` files
- `02_evidence/profiling/doc_profiles.csv` (filtered), `02_evidence/profiling/*.json` (targeted checks)
- `registry/entities.yaml`, `registry/key_normalisation.yaml`, `registry/open_questions.yaml`
- `registry/ontology/business.yaml` (objects, relationships, rules), `registry/ontology/data.yaml` (classes)
- `standards/naming.yaml`, `schemas/sttm.schema.json`
- `templates/sttm_template.yaml`, `examples.md`
- Open feedback in `04_mapping/feedback/CP4_sttm/` and `04_mapping/feedback/CP4b_business_logic/`
Do NOT go back to `00_inbox`. If a fact is missing, add evidence by feedback or a P2.3 rerun.

## Steps
1. One target table per business object at one grain. Start from the discovery roles: skip `staging`, and do not load tables marked `derive_instead`. Set `business_object` and `data_class`.
   - Shared master -> `target_kind: master`, `conformed_entity`, values as in `registry/entities.yaml`.
   - Other -> `target_kind: process` with FKs to masters.
2. Load pattern: must be in `allowed_load_patterns` of the data class (`data.yaml`).
3. Keys: `business_key` with `key_rule`; `surrogate_key` = hash (name ends `_sk`); `primary_key` = surrogate key.
4. Sources and joins: alias, filter, dedup; each join has `condition`, `type`, `cardinality` (from profiling).
5. Columns: `rule`, `source`, `transform`, `key_role`, `description`, `provenance: {evidence: [E-...], profiling: ...}`, `confidence`.
6. FKs: `fk: {entity | table, column, cardinality, orphan_policy, lookup_on}`.
   - `entity`: a shared master (registry). `table`: another target table of THIS STTM (for example line -> header). Exactly one.
   - `column`: the surrogate key of the parent. The FK in silver is always ONE surrogate-key column, also for composite keys.
   - `lookup_on`: one item per parent business-key column, in order: a SQL expression, or `{expr, key_rule}` to normalise it.
     Required for composite keys (for example `[l.MANDT, l.EBELN]` -> header key `[client, po_number]`). With `lookup_on` the lookup code is generated; without it, it stays a TODO.
   - `orphan_policy: unknown_member` only for shared masters; use `reject` (rows go to `<table>_quarantine`) or `allow_null` for same-source tables.
   - A relationship child -> parent must exist in `business.yaml` (N:1 or 1:1, in the right direction).
7. Business logic: `business_logic: true`, `business_rule: BR-<DOM>-<nnn>`, exact formula in `transform`. This needs CP4b.
8. Weak evidence: `confidence: low` + `open_question: Q-xxxx`. Keys and business logic cannot rest only on low evidence.
9. Feedback `code` items: use the snippet in `transform` only if it follows `standards/`; cite the feedback id in `notes`.
10. **Scope.** Do not use a source table with scope `out_of_scope` or `derive_instead`, or a column with scope `out_of_scope`
    (login times, IPs, session ids). If a person decided otherwise, add `scope_override: {reason: "<who, why>"}` on the source or column.
    Never map a `secret_or_token` column.
11. **Privacy.** Each column fed by a `personal_data` column gets `privacy: {class: personal, handling: keep_tagged | mask | hash, reason}`.
    Decided `mask` at CP2 (`in_scope_masked`) -> `mask` or `hash`. `hash` needs `sha2(...)` in `transform`. A person-name in a business key:
    prefer `hash`, or a surrogate code from the source. `standards/privacy.yaml` gives the tags and the mask function.
10. Run `@p4-2-sttm-validate`. Keep `status: draft` until the review passes.

## Decision table: data class -> load pattern
| data_class | allowed | normal choice |
|---|---|---|
| master | scd2, merge | scd2 |
| reference | merge, overwrite | merge (SCD1) |
| event | append, merge | merge if corrections arrive, else append |
| agreement | scd2, merge | merge with valid_from / valid_to |
| measure | append, merge, overwrite | merge by subject + period |
| snapshot | append, overwrite | append with snapshot_date |
| bridge | merge, overwrite | merge |

## Done when
`python tools/p4_2_validate_sttm.py sources/<id>/04_mapping/sttm.yaml` shows no errors, and every low-confidence column has a question.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p4-1-sttm-author --comment "..." --blocks CP4_sttm`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
