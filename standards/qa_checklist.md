# QA checklist (PLACEHOLDER — replace with the client's checklist)

Each item has an ID. Each ID must have one function in `lib/qa_checks.py`.
When the client adds a check, add the item here AND a function there in the same PR.

| ID | Check | Pass rule | Function |
|---|---|---|---|
| QA-01 | Row count reconciliation | silver rows = bronze rows after STTM filter and dedup (tolerance 0% unless stated) | `qa01_row_count_reconciliation` |
| QA-02 | Schema matches STTM | every STTM column exists with its type; audit columns exist | `qa02_schema_matches_sttm` |
| QA-03 | Primary key unique | no duplicate and no null PK values | `qa03_pk_unique` |
| QA-04 | Not-null columns | columns with `nullable: false` have no nulls | `qa04_not_null` |
| QA-05 | Foreign key integrity | every FK value exists in its parent: shared master or same-source table (orphan policy applied) | `qa05_fk_integrity` |
| QA-06 | SCD2 validity | one current row per business key; the current row is the latest; no inverted, overlapping, or gapped periods | `qa06_scd2_validity` |
| QA-07 | Key patterns | normalised keys match the rule pattern in `registry/key_normalisation.yaml` | `qa07_key_patterns` |

Unknown member: every shared master has one row with `UNKNOWN_SK` (`lib/keys.py`). QA-01, QA-04, and QA-07 ignore it;
QA-05 fails when a child table uses it for an FK whose `orphan_policy` is not `unknown_member`.
Shared masters: source notebooks are checked on their staging table; the master build is checked on the master.

Applicability: `lib/qa_rules.py`. QA-05 only for tables with FKs, QA-06 only for SCD2 tables, QA-07 only for tables with normalised keys.
Every other ID in this table is REQUIRED for every mapped table, so a new client item is enforced at CP5 by default
(until its function exists, the runner reports it as `error`).

Add client items below, for example: freshness, partition completeness, PII tags, table comments.
