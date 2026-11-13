# V1.4 port guide — moving the upgrades into the V1.3 code

For the maintainers who own the V1.3 framework. V1.4 keeps the V1.3 sequence and checkpoints; each row says which
V1.4 module upgrades which V1.3 part, and what to adapt. The V1.4 modules are in `b2s/` (repository root) and were built and
tested outside the V1.3 system (104 tests, fake application S90_yardops), so paths and names may differ from V1.3.

Port in this order: the rows are grouped so each group works on its own.

## 1. Foundations (port first — the rest depends on them)
| V1.4 module | Replaces / extends in V1.3 | Adapt |
|---|---|---|
| `layout.py` (write guard, `PHASE_OF`) | `x_layout.py` | Merge the guard into `x_layout`: in test mode writes only under the test root (DC-02). Map stems to the V1.3 folders you use (`work/<phase>/`, `review/`, `state/`) in one table. |
| `store.py` (atomic, write-once, O_EXCL lock, ids, events, lease) | id allocation in `x_questions.py`, feedback ids | Use one allocator for all ids (DC-09). Run checks K-01 (rename) and K-02 (O_EXCL) on `/Workspace` first; if K-02 fails, use the lease. |
| `versions.py` (`<name>.vNNN.<ext>` + `.meta.json`) | every JSON / YAML / Excel output | Every state file becomes versioned and write-once. Sidecars record input versions; the navigator uses them. |
| `items.py` (`E-`, `Q-`, `A-`, `IN-`, `CR-`, `IF-`, `OP-`, `APR-`) | evidence register CSV, questions, feedback items | One file per item version; CSV / Excel become generated views. Add `root_source` (DC-05) and `authority_class` (DC-13). |
| `steps.py`, `navigator.py` | navigator, `fresh_run` handling | Step ids are the V1.3 ids (P1, P2.1, P2.2, P2.2b, P2.3, P3, P4.1). Fingerprints include step version and effective settings (DC-12); `fresh_run` stays a one-run flag. |

## 2. P1 bronze baseline
| V1.4 module | V1.3 part | Adapt |
|---|---|---|
| `baseline/engine.py`, `profile.py` | S0, S1, S2, S5 | Keep your profiler if you prefer: it plugs in through the `profiler` slot (`@fw-integrate`). Take over: redaction before write (R-01), `removed_by_rule`, `no_key_within_limits` vs `no_key` (DC-10/11), stable open-point ids (DC-03), base-table fingerprint with view text (DB-07). |
| `baseline/readers.py` `SparkReader` | Spark access | Not run on Databricks yet: check K-04 (sampling through views). |

## 3. P2 documents, application understanding, scope
| V1.4 module | V1.3 part | Adapt |
|---|---|---|
| `documents.py` | P2.1a inventory, P2.1b triage, P2.1c extracts | Inbox keeps sub-folders; same-name-different-content = compare; extracts redacted. |
| skill `p2-2-compare` | P2.2 | Writes `documents/comparison`; contradictions raise a `Q-`. |
| skills `p2-2b-understand`, `x-research`; `research.py`; `models.py`; `viewer/` | **new step P2.2b** | Glean conceptual rounds first, raw reply saved first (DC-04); dependencies / process / conceptual models in YAML with Mermaid and the HTML viewer. |
| `columns.py` (`build_columns`, `set_scope`) | P2.3 scope proposal | Column meaning known / inferred / unclear; only `unclear` columns may go to a Glean column round; worker decisions kept on reruns. Fixes the P2.2 / P2.3 order (F-01). |

## 4. P3 central model and P4 STTM
| V1.4 module | V1.3 part | Adapt |
|---|---|---|
| `columns.draft_logical` | P3 central model | Uses your S3 join results when ported (not in V1.4 M1). |
| `sttm.py` | P4.1 slot, P4.2 validate | Canonical STTM; when the team STTM generator arrives, plug it in at P4.1 and keep the validator. |
| `plugins.py` + `plugins/sttm_export_excel_default` | P4.4 export | Your Excel and JSON STTM templates come in through `sttm_export_excel` / `sttm_export_json` (`@fw-integrate`). |

## 5. Checkpoints in the chat
| V1.4 module | V1.3 part | Adapt |
|---|---|---|
| `approve.py`, skill `x-approve`, `rules/approvals.md` | gate notebook, `approvals.jsonl` | Checkpoints CP1–CP4 are approved in the Genie chat: `I, <name>, approve CP3 logical.v004.` The request keeps versions and hashes; the record refuses a changed file, a wrong version, a missing name. Migrate existing `approvals.jsonl` entries into `APR-` items with `how: notebook`. CP3b, CP4b: keep the V1.3 mechanism until they are moved to the chat. |
| `handoff.py` | H1 | Readme opens with the self-approval statement and the known / assumed / unknown counts. |

## 6. Rules and skills
| V1.4 | V1.3 | Adapt |
|---|---|---|
| `AGENTS.md` (< 6,000 characters) + `rules/*.md` | `AGENTS.md` + `rules/*.md` | Merge the must-follow rules; keep your existing rule files and add `approvals.md`, `files-and-versions.md`, `glean.md`, `privacy.md`, `modelling.md` where they differ. |
| skills `p2-1-triage`, `p2-2-compare`, `p2-2b-understand`, `p2-3-scope`, `p3-logical`, `p4-sttm`, `x-*`, `fw-integrate` | V1.3 skills | Replace step by step; the skill ids follow the V1.3 step ids. |

## 7. Not in V1.4 milestone 1
S3 joins, CP3b / CP4b in the chat, project-level approvals for shared ontology and masters, the input tracer port,
PDF / Word / PowerPoint extractors, edge routing in the viewer, Databricks checks K-01 to K-08.
