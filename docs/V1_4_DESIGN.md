# Bronze-to-Silver V1.4 — design

| | |
|---|---|
| Status | Built and pushed to `main`; **not yet run on a Databricks workspace** (see §14) |
| Updated | 2026-11-13 (after integration reviews I-17 and I-18) |
| Scope | The whole framework, P0–P6, for about 30 applications |
| Decisions | V1.3 sequence kept (I-15); agent runs every step (I-16); V1.4 **replaces** V1.3 (I-16, see §13) |
| History | Requirements, quiz answers and reviews: [`V1_3_REVIEW_WORKING.md`](V1_3_REVIEW_WORKING.md). Earlier drafts of this file are in git history. |

Every claim below that depends on Databricks carries a status: **verified locally** (by the test suite on a local
disk and the fake application), **verified on workspace**, or **not run**.

---

## 1. Purpose and principles

The framework moves the backend tables of an application from bronze to a modelled silver layer, with a
source-to-target mapping (STTM) as the contract between modelling and build. The worker and the client often do not
know everything; the framework moves forward with what is known, records what is not, and goes back when input
arrives.

1. **The agent runs the framework.** Genie Code runs every step — tools, skills and notebooks. The worker gives input and approves CP1–CP4 in the chat.
2. **Mark what you do not know.** Every model element, column and mapping is `known`, `assumed` (`A-` item) or `unknown` (`Q-` item, shown `?`). Questions never block before the STTM.
3. **Files are the state.** No tables are available for state. Each state file is written once with its version in the name; every change is an event.
4. **Everything can go stale, nothing goes silently wrong.** Each output records the input versions it was made from; a change marks dependents stale and the status shows the rerun plan.
5. **Personal data never reaches a file.** Values of sensitive columns are removed before anything is written.
6. **Understand the application before the columns.** Bronze, documents and Glean conceptual rounds first; Glean column rounds only for columns the framework cannot explain.
7. **The framework is read-only for workers.** Their own notebooks and templates come in as plug-ins (`@fw-integrate`); maintainers move good ones into core.

## 2. Sequence (V1.3, kept)

```
P0 Setup ─ P1 Bronze baseline ─(CP1)─ P2 Documents, application understanding, scope ─(CP2)─
           P3 Central model ─(CP3)─ P4 STTM ─(CP4)─ H1 ─ P5 Build and QA ─(CP5 auto)─ P6 Release ─(CP6 auto)─ H2
```

| Step | Name | Runs | Outputs (stem → `work/<phase>/`) | Skill |
|---|---|---|---|---|
| P0 | Setup, workspace checks, first-use integration, register application | agent: `nb_doctor`, `00_start_here`, `@fw-integrate` | `project.yaml`, `capabilities`, plug-ins | `@p0-setup` |
| P1 | Bronze baseline: S0 inventory, S1 profile, S2 grain and keys, S5 report | agent runs `nb_p1_baseline` (client profiler plug-in first if integrated) | `baseline/tables/*`, `baseline/summary`, open points `OP-` | `@p1-baseline` |
| CP1 | Decision per open point; Glean check first | worker, chat | `APR-` | `@x-approve` |
| P2.1 | Documents: inventory, triage, redacted extracts | agent runs `nb_p2_documents` | `documents/inventory`, `documents/triage`, `documents/extracts/*` | `@p2-1-triage` |
| P2.2 | Compare documents with the baseline | agent | `documents/comparison` | `@p2-2-compare` |
| P2.2b | Application understanding and models (new in V1.4) | agent, Glean conceptual rounds | `understanding/app_brief`, `models/dependencies`, `models/process`, `models/conceptual` | `@p2-2b-understand` |
| P2.3, P2.4 | Scope, privacy, column meanings; questions and assumptions | tool + agent | `columns/columns`, `scope/scope` | `@p2-3-scope` |
| CP2 | Brief, models, scope (nothing left in review) | worker, chat | `APR-` | `@x-approve` |
| P3 | Central model: logical silver model | tool draft + agent | `models/logical` | `@p3-logical` |
| CP3 | Central model — **required before P4** | worker, chat | `APR-` | `@x-approve` |
| P4.1–P4.4 | STTM: draft from the approved model, validate, review, export | tool + agent | `sttm/sttm`, `models/mapping`, exports | `@p4-sttm` |
| CP4 → H1 | STTM with a decision per open question and assumption | worker, chat | `APR-`, `handoff/H-nnn` | `@x-approve` |
| P5.1, P5.4 | PySpark notebooks from the STTM; shared master builds (dev schema only) | tool + agent | `build/index`, `build/masters` | `@p5-1-codegen`, `@p5-4-masters` |
| P5.2, P5.3 | QA on dev silver (agent runs `nb_p5_qa`); code review in a new chat | agent | `qa/plan`, `qa/results`, `build/code_review` | `@p5-2-qa`, `@p5-3-code-review` |
| CP5 | Code and QA — automatic checks | framework | `APR-` (how: automatic) | `b2s cp-auto` |
| P6.1 → CP6 → H2 | Readiness package; automatic CP6; handoff to deployment | tool | `release/readiness`, `handoff/H2-nnn` | `@p6-1-release` |

Notebook names: `00_start_here`, `nb_doctor`, `nb_p1_baseline`, `nb_p2_documents`, `nb_p5_qa`.
CP3b (key rules) and CP4b (business logic) are not separate checkpoints in V1.4: key rules are part of CP3 (shared
masters in `_project/entities.yaml`), business-logic columns are decided per item at CP4.

## 3. How the agent runs notebooks (one way, written down)

- Genie Code opens the notebook in the framework folder, sets its widgets (`project_root`, `app`, `run_by = genie`, step-specific) and runs all cells **interactively in the worker's session**. There are no jobs.
- Every event the notebook writes records `run_by` (`genie` or `person`), the workspace user (`current_user()`), and `via: notebook`.
- Each notebook ends with one line `B2S_STATUS {json}`; the agent reads that first. A run that stops at the time budget (25 minutes) sets `partial` and resumes on the next run.
- A notebook runs headless with widget defaults (`project_root` falls back to `B2S_PROJECT`).
- A person may run any notebook the same way (`run_by = person`).
- Status: **verified locally** (notebooks parse, are Spark Connect safe, have no `%pip`); **not run** on a workspace.

## 4. Two areas: framework and project

| | Framework (this repository) | Project folder |
|---|---|---|
| Holds | `b2s/`, `notebooks/`, `skills/`, `rules/`, `AGENTS.md`, `plugins/`, `registry_template/`, `lib/`, `standards/` | `project.yaml`, `_project/` ontology, `apps/<app>/…`, `events/`, `state/`, plug-ins, contributions |
| Changed by | maintainers (Git) | the agent and tools (files) |
| Version | `FRAMEWORK_VERSION` | `project.yaml` pins the framework **version**, never its path |
| Location | any folder; found at run time (names with spaces and dots, moves: verified locally) | not under `/Workspace/Shared` in any spelling (`/Shared/...` included) |

Genie reads `AGENTS.md` from the parent folders of the open file. The project folder is not under the framework
folder, so it has its own short `AGENTS.md` that points to the framework folder found at run time
(`refresh_project_agents`). Skills are installed where Genie loads them (`b2s install-skills <folder>`, version stamp,
`status --brief` warns on a mismatch). `MANIFEST.json` (detection of edited framework files) is **planned**.

Per application: `inbox/`, `uploads/`, `work/P1…P6/`, `review/approvals/`, `state/items/<kind>/<bucket>/`,
`handoff/`. Events: `events/<day>/<hour>/`. Folders stay small (≈100 item ids per bucket) because listing large
folders on `/Workspace` is slow.

## 5. File state, versions and audit

- **Write-once versions:** `<name>.vNNN.<ext>` with a sidecar `.meta.json` (content hash, input versions, reason, fingerprint, framework version, event). A new version only when the content changes; the latest is the highest number.
- **Items:** one JSON file per item version (`E-` evidence, `Q-` question, `A-` assumption, `IN-` input, `CR-` change request, `IF-` document, `OP-` open point, `APR-` approval). Sequential ids from a lock-protected counter; open points have stable hash ids.
- **Writes:** temporary file + rename (K-01). **Locks:** `O_EXCL` lock files (K-02) or `mkdir` locks, as recorded by the doctor in `project.yaml capabilities.lock_mode`. One writer per application through a lease.
- **Write guard:** in tests every write outside the test root fails.
- **Data only:** generated files and items hold data, never text addressed to an agent. Agent instructions live only in `AGENTS.md`, `rules/` and `skills/`.
- **Audit:** events (who, how, `run_by`), sidecars (made from what), approvals (exact versions and hashes, verbatim statement). Tamper-evident, not tamper-proof.
- Status: **verified locally**, incl. parallel processes; K-01 / K-02 **not run** on `/Workspace` (`nb_doctor`).

## 6. Stale detection

Fingerprint of an output = step version + effective settings + content hash of each input version (§5). For bronze:
base-table Delta version and the view text of each view on the path; views over views are followed with one shared
parser (`b2s.baseline.views`) used by every reader. A table whose history the user cannot read gets version `None`
and its row count as the change signal. `b2s status` lists stale steps, why, and the rerun order.
Status: **verified locally** with the fake reader; Spark reader **not run**.

## 7. P1 bronze baseline

- Profiles are computed **where the data is**: the Spark reader runs one aggregation pass per table (counts, approximate distincts, min/max, lengths, value kinds) and small group-bys for top values and shapes; no rows are collected as Python lists. The sample is a deterministic hash filter (no unordered `limit`).
- Key search: declared keys first, single and composite keys with an exact check on the full table (one pass per candidate), near keys with the duplicate count, `no_key_within_limits` vs `no_key` with the limits, `removed_by_rule` per table. CDC load-version and audit columns are left out (patterns in `_project/information.yaml`).
- Copies: same business columns after unifying abbreviations (`plt_cd` = `plant_code`, list in `_project/information.yaml`), audit and CDC columns left out, same content.
- Redaction before any write; top values only for low-cardinality code columns, never for keys.
- A client profiler notebook can replace the core profile (plug-in, §11); key search, classification and redaction still run in the framework.
- Same contract tests for every reader (`tests/test_reader_contract.py`): local reader **verified locally**; Spark reader runs with `RUN_SPARK=1` (**not run**).

## 8. P2 documents, application understanding, scope

- P2.1: duplicates (keep the clean name), same name with different content (compare), unreadable files listed, extracts redacted.
- P2.2: each document fact confirms, contradicts or adds to the baseline (`documents/comparison`).
- P2.2b: app brief and three models (dependencies, process, conceptual) from bronze, documents and Glean.
- Glean: conceptual rounds first; column rounds only for columns P2.3 marks `unclear`; raw reply saved first; claims carry `root_source` and only different roots corroborate; paste mode is the default, the connector is optional and no connector tool names are in the code.
- P2.3: column meaning `known | inferred | unclear`; scope and privacy proposal; worker decisions (given in the chat, saved by the agent) survive reruns.

## 9. Models and the viewer

Five models — dependencies, process, conceptual, logical, mapping — as YAML (truth), Mermaid (`.mmd`, the
accountability record) and a self-contained HTML viewer. `b2s check` requires the YAML, the Mermaid and the graph
inside the HTML to be identical. No overlapping boxes or labels; WCAG contrast ≥ 4.5:1 (7:1 for key badges) in light
and dark. Status never by colour alone. Status: **verified locally**.

## 10. Checkpoints in the chat

| Checkpoint | Main files in the statement | Blocks |
|---|---|---|
| CP1 | `summary.vNNN` + a decision per open point | — |
| CP2 | `app_brief`, `dependencies`, `process`, `conceptual`, `scope` versions | CP3 (chain) |
| CP3 | `logical.vNNN` | **P4** |
| CP4 | `sttm.vNNN` + a decision per open question / assumption | **handoff H1** |
| CP5, CP6 | automatic checks | P6, H2 |
| PLUGIN | `<plug-in>.v<version>` | use of a project plug-in |

- The agent runs `b2s approve request`, shows the chat text; the template is pre-filled except the name: `I, <your name>, approve CP3 logical.v004.`
- The worker's reply is passed **verbatim on stdin** (`--statement-file -`), never through shell quoting.
- Refused: no name, an agent name (Genie, assistant, …), a name not in `project.yaml approvers` (when set), a wrong point or version, a file changed after the request, an undecided item.
- One worker per application, no maker-checker: the handoff states that it is self-approved and quotes the statement.
- Status: **verified locally**.

## 11. Plug-ins and first use

Slots: `profiler`, `sttm_export_excel`, `sttm_export_json`, `sttm_import_excel`, `doc_extractor`, `key_rules`.
A plug-in is `kind: python` (adapter implements the slot) or `kind: notebook` (the client notebook, unchanged; the agent
runs it with the widgets from `run_plan`; `convert(run_dir)` maps its output; the contract test runs `convert` on
`sample_output/`). A project plug-in overrides core only after `approve PLUGIN`. On first use, `@p0-setup` asks for
the client's profiler notebook and STTM templates and integrates each with `@fw-integrate`; workers send good
plug-ins to maintainers as contribution packages. Status: **verified locally** with a sample profiler; the real client
profiler and STTM templates are **not yet integrated** (need one real example of each input and output).

## 12. P5 build and P6 release

Generated PySpark notebooks per target table and per shared master (safe to rerun: GENERATED cells refreshed, TODO
cells kept, REVIEW blocks when the STTM changed), dev schema only; QA plan and QA notebook on dev silver; code review
in a new chat; CP5 and CP6 automatic; H2 package. Status: generation and checks **verified locally**; generated
notebook code and the QA notebook **not run** on Spark.

## 13. Relation to V1.3

V1.4 **replaces** V1.3: the repository is the whole framework; the V1.3 sequence, checkpoints and folder idea stay.
Existing V1.3 project state (for example S01_dpof) moves into V1.4 with a migration tool (**not built yet**: it needs
one sample of each V1.3 state file — `sources.yaml`, `approvals.jsonl`, CP1 decisions, open points, the evidence CSV,
Glean replies). See [`V1_4_MIGRATION.md`](V1_4_MIGRATION.md) for the feature status and the migration plan.

## 14. Verification status

| Area | Verified locally | Verified on workspace | Not run |
|---|---|---|---|
| File state, versions, locks (O_EXCL and mkdir), write guard | yes | — | K-01, K-02 on `/Workspace` (`nb_doctor`) |
| Stale detection, rerun plan, handover (`status --brief`) | yes | — | — |
| P1 engine with the local reader | yes | — | — |
| Spark reader: views → base tables, aggregation profile, one-pass uniqueness, quoting | — | — | yes (`RUN_SPARK=1` tests, `nb_doctor` K-04) |
| P2 documents, comparison file, scope, column meanings | yes | — | PDF / Word / PowerPoint extractors |
| Models, Mermaid check, viewer layout and contrast | yes | — | K-08 (CDN) |
| Checkpoints in the chat, chain, handoffs | yes | — | K-07 (audit logs) |
| Plug-ins incl. notebook plug-ins | yes (sample) | — | real client profiler and templates |
| P5 code generation, masters, QA plan, CP5/CP6 | yes | — | generated Spark code, `nb_p5_qa` |
| Install skills, project AGENTS.md pointer, moved framework folder | yes | — | Genie skill folder on a workspace |
| Migration from V1.3 | — | — | not built |

Test counts come from the test run (`python -m pytest`), not from this file.

## 15. Workspace checks (`nb_doctor`)

| Id | Check | If it fails |
|---|---|---|
| K-01 | atomic rename on `/Workspace` | stop: state cannot be written safely |
| K-02 | exclusive create (`O_EXCL`) | `mkdir` locks are used (`capabilities.lock_mode`) |
| K-03 | folder permissions readable; who can read the project folder | check by hand in the workspace UI |
| K-04 | hash sample the same through a view and its base table | profile base tables, not views |
| K-05 | lineage system tables readable | view text parsing only |
| K-06 | libraries (`pyyaml`, `openpyxl`, `jsonschema`) in the notebook's serverless environment | add them to the environment |
| K-07 | audit logs mark Genie actions | manual; `run_by` in events remains the record |
| K-08 | workspace HTML may load a CDN script | the viewer works without it |

## 16. Open owner decisions and inputs needed

| Id | Decision or input |
|---|---|
| Q-01 | Version naming: 1.4.0 vs the public 2.4.0 tag |
| M-01 | One sample of each V1.3 state file for the migration tool (§13) |
| M-02 | One real input and output example of the client profiler notebook and of the STTM Excel and JSON templates |
| M-03 | `project.yaml approvers`: names allowed in approval statements (optional) |
