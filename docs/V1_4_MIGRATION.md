# From V1.3 to V1.4

V1.4 **replaces** V1.3. The V1.3 sequence (P0–P6) and checkpoints (CP1–CP6) stay; what runs inside them is new.
This file lists every V1.3 engine feature with its status in V1.4, and how existing V1.3 project state moves over.

Status values: **ported** (same behaviour, verified locally), **replaced** (a different V1.4 mechanism does the job),
**not yet** (planned, not built), **dropped**.

## 1. V1.3 features

| V1.3 feature | V1.4 status | Where in V1.4 |
|---|---|---|
| S0 inventory, S1 column profile, S2 grain and keys, S5 report | ported | `b2s/baseline`, `nb_p1_baseline` |
| Fixed-seed sample (max 5M rows) | replaced | deterministic hash filter computed in Spark, profile by aggregation |
| Load-version (CDC) columns out of the key search | ported | `_project/information.yaml column_patterns.cdc` |
| Audit columns out of the key search | ported | `column_patterns.audit` |
| `*_nm` columns allowed when a table has no code column | ported | `b2s/baseline/engine.py key_candidates` |
| Keys cited by a Glean answer checked exactly, any width | **not yet** | planned: evidence claims about keys become extra key candidates |
| Copied bronze tables found after unifying abbreviations (`plt` / `plant`) | ported | `business_signature`, `information.yaml abbreviations` |
| `@x-doc-duplicates` | replaced | P2.1 inventory (exact copies, same name with different content) |
| CP1 decisions per open point; decision stale when the point changes | ported | CP1 in the chat; stable open-point ids |
| CP1 Glean check before a client question | ported | `@p1-baseline` step 3 |
| Glean: one JSON object per topic, several rounds; reopen a closed phase | ported | `b2s/research.py` |
| `fresh_run` as a one-run flag | ported | `nb_p1_baseline` |
| Time budget 25 minutes, resume; 1000 tables per source | ported | settings `time_budget_minutes`, `max_tables` |
| No writes to the catalog | ported | files only |
| AGENTS.md core + `rules/*.md` with a link test | ported | `AGENTS.md`, `rules/`, `tests/test_m1_10_agents_cli.py` |
| `data_root`, `x_layout`, V1.2 folder names | replaced | project folder + `b2s/layout.py` (`work/P1…P6`, `review/`, `state/`) |
| Gate notebook with `approvals.jsonl` | replaced | checkpoints approved in the chat (`APR-` items) |
| CP5, CP6 automatic | ported | `b2s cp-auto` |
| V1.2 project defaults | ported | `project.yaml settings` |
| V1.2 bronze metadata snapshot | replaced | P1 baseline |
| V1.2 orientation pack | replaced | `b2s status --brief` (handover from the state) |
| V1.2 "ask one time" | partly | questions are reused by subject on reruns; a project-wide question register is **not yet** |
| Team profiling tool: functional-dependency hints (2NF/3NF), category value comparison, relationship hints, more table roles | **not yet** | planned for P3; the client profiler can come in as a plug-in now |
| S3 joins on in-scope tables | **not yet** | P3 uses conceptual relationships and baseline keys today |
| P4.1 slot for the team STTM generator | partly | P4.1 drafts the STTM; a `sttm_generator` plug-in slot is **not yet** |
| Journal per source and project knowledge base | replaced | events + `status --brief`; a knowledge base is **not yet** |

## 2. Moving V1.3 project state (migration tool — not built yet)

Planned command: `python -m b2s migrate-v13 --from <V1.3 data_root>/<source> --project <V1.4 project> --dry-run`.
It writes an id map (old id → new id) and changes nothing in dry-run mode.

| V1.3 state | V1.4 target |
|---|---|
| `sources.yaml` entry | `apps/<app>/app.yaml` (schemas, lookup schemas) |
| `approvals.jsonl` (e.g. AP-0001) | `APR-` items with `how: notebook`, `approval_mode: self`, the checkpoint and the file versions they covered |
| CP1 decisions | statuses of the matching `OP-` items |
| Open points `OP-01`, `OP-02` … | stable `OP-<hash>` items; the id map lists `OP-01 → OP-3f9a2c` |
| Evidence register CSV | `E-` items with `root_source` and `authority_class` |
| Glean replies | research rounds `GR-` with the raw reply saved write-once |

**Needed to build it:** one sample of each file above from S01_dpof (values may be masked).

## 3. Checks before the first real run

Run `notebooks/nb_doctor` in the workspace (K-01 … K-08), then `install-skills`, then `@p0-setup`.
