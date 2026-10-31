---
name: p2-2-bronze-discovery
description: Step P2.2. Discover the bronze tables of one source without reading all data - Unity Catalog metadata and lineage first (comments, tags, masks, declared keys, statistics, writers and readers), then grain and candidate keys, column profiles, cross-table value matching (foreign keys, cardinality), table roles, lineage order, business objects, table and column scope (application logs, audit, secrets, personal data), documents-vs-bronze gaps, and related tables outside the schema. Orchestrates parallel code tasks and one agent per decision card. Use after CP1, and when feedback asks for a data check.
---

# P2.2 Bronze discovery (phase P2, checkpoint CP2_evidence)

## Goal
Know what each bronze table IS (role, grain, links, business object) with numbers as proof.
Code does the heavy, repeatable work on samples and exact checks. You only decide what code cannot.
Method and references: `references/methods.md`.

## Two modes
- **Mode A - orchestrate** (one chat per source): plan, run code tasks, create cards, merge, write evidence.
- **Mode B - one card** (one NEW chat per card): answer one `cards/T-xxx.md`. Never two cards in one chat.

## Mode A - orchestrate
0. Read active instructions for this step (`sources/<id>/instructions.yaml`, step `p2-2-bronze-discovery` or `all`) and their files.
1. Apply open feedback for `CP2_evidence` (for example a `data` item: table + filter to check).
2. Plan: `python tools/p2_2_discover.py plan <id>` -> `02_evidence/discovery/plan.yaml` and `job.json`.
3. Run the code tasks, ONE of:
   - large source: create a Databricks Job from `job.json` (for-each tasks run tables and link batches in parallel);
   - small source (< ~30 tables): in a notebook, `p2_2_discover.run(spark, "<id>", "all")`.
4. Check progress: `python tools/p2_2_discover.py status <id>`. A failed task: read its error, fix the cause, rerun only that task (`--stage profile --table ...`).
   What the run does, in order (each stage records what it could not read; nothing fails on missing metadata):
   - **catalog + meta** (no data read): `information_schema` tables, columns, tags, row filters, column masks, declared PK/FK
     constraints; `DESCRIBE DETAIL/HISTORY` (writers, last write, change data feed); `SHOW STATISTICS` (exact distinct and nulls);
     `system.access.table_lineage` and `column_lineage` (who writes and reads each table). -> `metadata/`, `lineage_view.json`.
   - **profile + keys**: one sampled aggregation per table, plus value-kind ratios (email, phone, IP, user agent, URL, JSON, UUID,
     token) by regular expression. Only RATIOS are kept. Values of personal, secret, and log columns are removed before any file is written.
     Declared keys and statistics are tried first, then verified.
   - **links + model**: declared FKs first, then candidates; roles, grain, lineage levels, business objects;
     **table scope** (in_scope, out_of_scope, derive_instead, review) and **column classes and scope** -> `column_scope.csv`.
   - **wider**: tables outside the schema with matching names, shared key columns, or lineage into this source (`related.csv`, R-cards);
     documents vs bronze (`doc_gaps.csv`, D-card); the same business object in other sources (`overlap.csv`, a CP3 item).
5. Read ONLY `02_evidence/discovery/summary.md`. Do not open `columns.csv` or part files unless a card needs one line.
6. Cards: code wrote `cards/T-xxx.md` for each decision it could not make (low-confidence role, no business object, no key, partial links,
   aggregates, table scope in review, columns to confirm), `R-xxx.md` for a related table outside the schema (include or not), and
   `D-001.md` for documented tables that bronze does not have (where are they?).
   Start one new chat per card with `@p2-2-bronze-discovery card sources/<id>/02_evidence/discovery/cards/T-xxx.md`.
   Cards are independent: several people or agents can work on them at the same time.
   Option - sub-agents on Databricks: run all open cards in parallel, one fresh LLM call per card, with answer checks:
   `from discovery.card_runner import run, databricks_llm; run("<id>", databricks_llm("<serving endpoint>"))`.
   The same runner can be a tool of a Databricks multi-agent app or an Agent Bricks supervisor later.
   A person still reads the merged `summary.md` before CP2.
7. When all cards have a `.result.yaml`: `python tools/p2_2_discover.py merge <id>`.
   Merge applies the answers, rewrites `summary.md`, and raises upstream items for `NEW:` business objects (CP3) and `raise_upstream` notes.
8. Bronze facts -> evidence: `python tools/p2_2_discover.py evidence <id>` (idempotent).
9. Log: `python tools/x_feedback.py log <id> p2-2-bronze-discovery --note "<tables>/<links>/<cards>"`.

## Mode B - one card
1. Read the card. Read `01_intake/source_brief.md`. Nothing else, unless the card names a line in a discovery file.
2. Decide only what the card asks. Use the allowed values on the card.
3. Write `cards/T-xxx.result.yaml` in the format on the card (template: `templates/card_result.yaml`).
4. If the problem belongs to an earlier phase (wrong file read, wrong grain in the brief), write it in `raise_upstream`. Do not work around it.
5. If you need more data, do not query bronze yourself. Write `raise_upstream: "need data check: <table> where <filter>"`.

## Decision guide (roles)
| Role | Signals | Data class | Usually |
|---|---|---|---|
| master (root) | one-column key, referenced by others, descriptive attributes | master | conformed entity |
| reference | small code list, code + description | reference | conformed entity or new classification object |
| transaction_header | own id + FKs + date, has child rows | event | process table |
| transaction_line | key = parent FK + line/sequence number | event | process table |
| event | time-stamped rows with FKs | event | process table |
| snapshot | key contains as-of / period date | snapshot | process table |
| bridge | key = two FKs, few columns | bridge | link table |
| aggregate | key = FKs/dates only, measures; derived from a detail table | measure | `derive_instead` (do not load) |
| staging | copy, backup, tmp, test | - | ignore |

## Scope: logs, audit, secrets, personal data
A column is judged by its NAME **and** its CONTENT **and** its Unity Catalog tags/masks, never by the name alone:
| Column class | Signals | Default scope |
|---|---|---|
| application_log | IP, user agent, URL content; or log names (login, session, browser) in a log-heavy table | out_of_scope (name only: review) |
| secret_or_token | password/token names, long hash or token content | out_of_scope, never mapped |
| personal_data | email or phone content, person-name or address names, a PII tag or a mask | review: keep (tagged), mask, or hash |
| audit_metadata | created/updated by/at, load ids | technical only |
| payload_or_free_text | JSON or long text | review (may hide personal data) |
In a card, answer `columns: {COL: keep | out_of_scope | mask}` only for the columns listed under "columns to confirm".
A personal-data column that is part of a key is still personal data: keep it only with privacy handling.

## Rules
- Never `SELECT *` a whole table. Never count distinct on every column of a big table. The budgets in `registry/ontology/information.yaml` (`discovery_budgets`) are limits, not targets.
- A key or FK is proven only by the exact checks code ran. A sample result alone is a hypothesis.
- "Matches only after normalisation" means a key rule is needed (CP3b). Say so; do not hide it.
- Use business object names from `business.yaml`. A new object is `NEW:<Name>` and goes to CP3 as a change request.
- Never copy values of personal-data, secret, or log columns into a card answer, evidence, or any file.

## Targeted checks (feedback `data` items)
`tools/p2_2_profile_table.py` profiles ONE table with given keys, FK checks, and a filter -> `02_evidence/profiling/fb_<FB-id>_<table>.json`.

## Done when
`summary.md` exists, all cards answered and merged, evidence written. Then `@p2-3-evidence-reconcile`.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p2-2-bronze-discovery --comment "..." --blocks CP2_evidence`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
