# V1.1 → V1.3 review — working file

Running file. Add each new input as an entry in the input log (section 8), then update the sections it changes.
Item ids are stable: do not renumber. Close an item by changing its status, not by deleting it.

| | |
|---|---|
| Started | 2026-11-13 |
| Last update | 2026-11-13 (input I-05) |
| Baseline in this clone | public repo `bronze-to-silver-databricks` 2.4.0, commit `db4fc1b` — matches **V1.1** |
| V1.3 code | not in this clone. All V1.3 items below come from the owner's summaries, not from code review |

Status values: **Done** (in code or rules), **Partly done**, **In progress**, **Planned** (in `PLAN_V1_3.md`, not built), **No change** (same spec as V1.1).

---

## 1. Summary

The main change is the order. V1.1 reads the documents first and checks bronze second. V1.3 profiles bronze first, and then reads the documents against that baseline.
P3 to P6 are the same at spec level, except: fewer human approvals (CP5, CP6 automatic), S3 joins only on in-scope tables, and P4.1 is an empty slot for the team STTM generator.

V1.2 sat between them. It added project defaults, a bronze metadata snapshot, an orientation pack, and the "ask one time" rule. V1.3 keeps these. The full bronze baseline replaces the V1.2 metadata snapshot.

**Review verdict so far:** the direction is right. Three risks (R-01 to R-03) weaken guarantees that V1.1 had. Fix them before step 11 (migration of real sources).

---

## 2. Version mapping

| Name used here | What it is |
|---|---|
| V1.1 | design in the public repo, tagged **2.4.0** |
| V1.2 | intermediate: project defaults, bronze metadata snapshot, orientation pack, "ask one time" |
| V1.3 | in progress, described in `PLAN_V1_3.md` and the source playbook |

Open: the public tag (2.4.0) and the internal names (V1.x) do not match. See Q-01.

---

## 3. Change register (V1.1 → V1.3)

### 3.1 Overall principles and design

| Id | Change | Decision | Status |
|---|---|---|---|
| C-01 | Data first: profile bronze first; documents are read against the profile | D4 | Done |
| C-02 | Code and data separate: project data in `settings.yaml: data_root`; `x_layout.py` makes all paths; V1.2 folder names still work; migration tool | D1 | Done |
| C-03 | No sample systems; tests make their own data | D3 | Done |
| C-04 | No Git for now: framework stays a workspace folder; approval in a gate notebook under the person's name, written to `approvals.jsonl` | D2 | Done |
| C-05 | Fewer approvals: only CP1 to CP4 need a person; CP5 and CP6 use automatic checks | D11 | Partly done |
| C-06 | Questions do not stop the flow: Glean answers become assumptions; a client question does not block the next step | D11 | Planned (step 7) |
| C-07 | One notebook per section, run cell by cell; `Result:` note from real output after each cell; check cell by a different method; status cell | — | Done |
| C-08 | Run limits: 25-minute time budget, resume on next run; max 1000 tables per source (V1.1: 200) | D6 | Done |
| C-09 | One profiling engine: team profiling tool methods move into the framework engine | D7 | Partly done |
| C-10 | No writes to the catalog: no scratch schema or volume; reads through views; JSON in `work/discovery/_scratch/` | D8 | Done |
| C-11 | Rules in parts: short AGENTS.md core + `rules/*.md`; a test checks the links | — | Done |

### 3.2 P0 Setup

| Id | Change | Status |
|---|---|---|
| C-12 | Set `data_root` once for the project | Done |
| C-13 | First new source creates `_project/` from `registry/` and writes an AGENTS.md in the data root | Done |
| C-14 | Patterns for audit and load-version columns, and abbreviations (`plt` = `plant`), set in `information.yaml` | Done |

### 3.3 P1 Register and bronze baseline (V1.1: "Intake and focus")

| Id | Change | Status |
|---|---|---|
| C-15 | P1 reads only bronze data (V1.1: inventory, triage, brief of documents) | Done |
| C-16 | P1.1 Register: one or more bronze schemas and lookup schemas | Done |
| C-17 | P1.2 Inventory (S0): metadata, row counts, base table of each view; empty tables; tables with the same row count | Done |
| C-18 | P1.3 Column profile (S1): fixed-seed sample, max 5M rows; per column: empty values, length data, **most frequent values** | Done |
| C-19 | P1.4 Grain and keys (S2): candidate keys on the sample, exact check on full table; uses CDC load-version columns, leaves audit columns out, checks Glean-cited keys of any width, allows `*_nm` columns when no code column exists | Done |
| C-20 | P1.5 Baseline report (S5): Excel, summary page, JSON; open points: no key, near-key, copy of another table, empty tables | Done |
| C-21 | CP1 Bronze baseline: reviewer decides each open point (accept, change, client question, defer); decision goes stale when its point changes | Done |
| C-22 | CP1 Glean check: before an open point becomes a client question, ask Glean; one JSON object per topic, several rounds | Done |

### 3.4 P2 Documents and scope (V1.1: "Discovery and evidence")

| Id | Change | Status |
|---|---|---|
| C-23 | P2 reads documents against the bronze baseline (V1.1: P2 profiled bronze) | Done |
| C-24 | P2.1a Inventory: exact file copies, keep the clean name; same name + different content = "compare" | Done |
| C-25 | P2.1b Triage: reads only the table of contents; core / supporting / background / ignore | Done |
| C-26 | P2.1c, P2.1d: document profiles and source brief | In progress |
| C-27 | P2.2 Compare with baseline: each fact confirms, contradicts, or adds. **Open: scope cards run before the comparison; the plan wants the opposite** | Partly done |
| C-28 | P2.3 Scope proposal: agent proposes in-scope tables from the data; documents change the list (V1.1: documents set the scope) | Planned |
| C-29 | P2.4 Questions and assumptions: questions stay open but do not block | Planned |
| C-30 | No documents: skip document review; gaps become assumptions | Planned |

### 3.5 P3 Joins and central model

| Id | Change | Status |
|---|---|---|
| C-31 | S3 joins run only on in-scope tables (V1.1: all tables) | Planned |
| C-32 | New methods from team tool: functional dependency hints (2NF, 3NF), category value comparison, relationship hints (header/detail, lookup), more table roles (bridge, history) | Planned |
| C-33 | CP3, CP3b | No change |

### 3.6 P4 Mapping

| Id | Change | Status |
|---|---|---|
| C-34 | P4.1 STTM is an empty slot for the team STTM generator, delivered later | Planned (D12) |
| C-35 | P4.2 validate, P4.3 review, P4.4 export, CP4, CP4b, H1 | No change |

### 3.7 P5 Build

| Id | Change | Status |
|---|---|---|
| C-36 | S4 deep quality runs only on silver, new `lib/quality_profile.py` | Planned |
| C-37 | CP5 needs no person; automatic checks replace the approval | Changed |
| C-38 | Codegen, code review, master build | No change |

### 3.8 P6 Handoff

| Id | Change | Status |
|---|---|---|
| C-39 | Readiness package, H2 | No change |
| C-40 | CP6 needs no person | Changed |

### 3.9 X Feedback and rerun

| Id | Change | Status |
|---|---|---|
| C-41 | `fresh_run`: recompute all tables after a framework fix | Done |
| C-42 | Closed research phase can reopen with a reason and an extra budget | Done |
| C-43 | Journal per source; shared knowledge base per project, grouped by phase | Planned (step 9) |

---

## 4. Risks (fix before step 11)

| Id | Risk | Caused by | Proposed fix | Status |
|---|---|---|---|---|
| R-01 | **Personal data can reach files before classification.** S1 writes most frequent values to Excel/JSON/summary. Scope and privacy move to P2.3, after S1. V1.1 stored only ratios and shapes for sensitive columns. **I-05 confirms exposure:** data root is in `/Workspace/Shared` (usually readable by all workspace users) and the baseline report and profiles hold top values and key data | C-15, C-18, C-28, DB-12 | **Now:** restrict access on the data root (DB-12). **Design:** run the name + content + tag classifier inside S1; strip values of sensitive columns before any write; `core.redact_values` on by default and not switchable per run without a logged reason. Test with a fixture of emails/phones that asserts no raw value appears in any S1 output | Open — raised |
| R-02 | **Approvals are not protected against agents.** V1.1: approval only in a PR with CODEOWNERS. V1.3: `approvals.jsonl` with a typed name; an agent that can write files can append to it. **I-05: Genie Code runs with the user's own permissions**, so `current_user()` and UC grants cannot tell the agent from the person | C-04, DC-18, DB-01 | Identity checks alone do not work (see I-05). ~~Separation of duties~~ is not possible: **one worker per application, no maker-checker (I-09)**; Delta tables not available (RQ-01). V1.4 accepts the risk and reduces it: deliberate approval in the gate notebook only (one-by-one decisions, typed confirmation with pack hash), Genie rule never to approve, handoff statement to team 2 (self-approved, assumptions, Genie-made items), audit events. **Check (K-07):** whether audit logs or notebook context mark Genie-run cells | Accepted risk — mitigated (V1_4_DESIGN §4, §12.3) |
| R-03 | **Assumptions can reach silver without a person seeing them.** Glean answers become assumptions, questions do not block, CP5 and CP6 are automatic | C-05, C-06, C-29, C-37, C-40 | Assumption = low confidence; keep the V1.1 rule that PK/BK/FK/business-logic columns cannot rest on low evidence; list all assumptions on the CP4 pack; automatic CP5 check that each privacy column has its mask/tag applied | Open |

---

## 5. Smaller findings

| Id | Finding | Related | Proposal | Status |
|---|---|---|---|---|
| F-01 | P2.2 order: scope cards run before the comparison, so they use stale input | C-27, C-28 | Agree with the plan: compare first, then scope. Next build task | Open |
| F-02 | S3 on in-scope tables only: a table wrongly scoped out never gets join analysis that would show it is needed | C-31 | Metadata-only join pass (declared keys, names, lineage) on all tables; value checks only in scope | Open |
| F-03 | P4.1 is an empty slot; P4 is the core deliverable | C-34 | Keep V1.1 `@p4-1-sttm-author` as fallback until the team generator arrives | Open |
| F-04 | No sample systems: new users lose the walkthrough | C-03 | Small script that generates a fake source so `next` can be shown end to end | Open |
| F-05 | Plan order: step 11 (migrate real sources) before step 13 (verify both layouts) means verifying on client data | Plan | Do step 13 before step 11 | Open |
| F-06 | Split rules: a link test proves the files are linked, not that agents read them | C-11 | Keep golden rules (privacy, never approve, never write prod) in the always-loaded core | Open |
| F-07 | CP2 now holds scope, evidence, and questions in one approval | C-27–C-29 | Keep scope and privacy decisions as a separate section of the CP2 pack | Open |
| F-08 | Glean is now a dependency | C-22 | Must degrade cleanly without Glean; Glean answers enter the evidence register with origin and confidence; reopen of a closed phase leaves an audit trail | Open |
| F-09 | Copy detection by same row count is weak alone | C-17 | Fine as a hint, since business-column comparison confirms it; do not raise an open point from row count alone | Open |
| F-10 | Version naming mismatch | — | Map 2.4.0 ↔ V1.1 in the upgrade doc and CHANGELOG | Open |

---

## 5A. Design change proposals from S01_dpof work (input I-04)

Proposals from the V1.3 work on real source **S01_dpof**, based on saved notes, the CHANGELOG, and the plan (code not run).
Each row: the problem seen, the proposed change, and the review comment.

### 5A.1 Cross-cutting

| Id | Problem seen | Proposed change | Review comment | Related | Status |
|---|---|---|---|---|---|
| DC-01 | Status records disagree: CHANGELOG says CP1 approved (AP-0001); HANDOVER.md and notes say not | One status record: `sources.yaml` + `approvals.jsonl`. A tool writes the status part of HANDOVER.md and the navigator view. No source status by hand in the CHANGELOG | Agree. CHANGELOG is for framework changes, never source status. Resolve the CP1 truth now (Q-05) | R-02 | Proposed |
| DC-02 | A test overwrote the live `_project/sources.yaml`; `x_layout` ignored the test temp root for registry files; stray `SX` folder in data root | Write guard in `x_layout`: without `B2S_TEST=1` a registry write stops with an error; with it, all paths go to the temp root. Test writes from each tool and compares md5 of live files | Agree, **do first** (data loss). Make it fail closed: `conftest.py` sets the test root automatically, and `x_layout` refuses any write to the real `data_root` while `PYTEST_CURRENT_TEST` is set. Delete the stray `SX` folder after checking it | — | Proposed |
| DC-03 | P1.5 renumbers open points at each build; research and decisions link to the wrong point | Stable id per open point from its kind + tables (short hash). OP-01 as display label only. Remove `match_point` | Agree. Use two hashes: an **identity hash** (kind + tables + columns) for the link, and a **content hash** (details, counts) for staleness (C-21). Otherwise a small statistic change breaks the link instead of making the decision stale | C-20, C-21 | Proposed |
| DC-04 | R7 Glean replies not saved; questions asked again | `x_research record` must not run until the raw reply file exists and is not empty. Save raw reply first, then parse. Same in paste mode | Agree. Also store the hash of the raw reply in the record, so evidence can point to the exact reply | C-22, F-08 | Proposed |
| DC-05 | Document IF-0021 and Glean came from the same root source; counted as one fact by hand | `root_source` column in the evidence register. Only evidence from different roots counts as corroboration. Auto flag when items disagree (e.g. E-0031 vs RT-018) | Agree; important. Glean often summarises the same documents, so without this Glean "confirms" documents with themselves | C-22, F-08, R-03 | Proposed |
| DC-06 | Compute had no `openpyxl`; session reset after long runs | Setup cell per template: install + check libraries, load notebook state from JSON parts. After reset, run one cell | Agree on state reload. For libraries prefer pinned versions on the compute or a job environment; `%pip` in a notebook restarts Python and loses state itself | C-07, C-08 | Proposed |
| DC-07 | `fresh_run` widget stayed "yes" in the S01 copy | "Fresh" is a one-run flag; runner clears it when the run ends; default "no" | Agree. Also log each fresh run in the run log with the reason | C-41 | Proposed |
| DC-08 | AGENTS.md near its 20,000-character limit | Only index + must-follow rules in AGENTS.md; rest to `rules/`; size check per rule file | Agree | C-11, F-06 | Proposed |
| DC-09 | Feedback-id test failed once (199 ids, not 200) | Feedback ids through the lock file, as `x_questions.py`. Run the test 20 times | Agree on the lock. 20 passing runs do not prove a race is gone; add a test with parallel processes that forces contention | — | Proposed |

### 5A.2 P1 Register and bronze baseline

| Id | Problem seen | Proposed change | Review comment | Related | Status |
|---|---|---|---|---|---|
| DC-10 | Engine missed a 14-column key: `max_key_size` 4, `key_pool_size` 8 | Report "no key within the limits" separately from "no key"; give the limits in the result | Agree. A 14-column key is itself a finding (likely a wrong grain or a missing column); flag it for CP1 | C-19, C-20 | Proposed |
| DC-11 | `DESC_NOT_KEY` rule removed `*_nm` columns silently | Per table, write the columns each rule removed into the key part file; show in the P1.5 report | Agree | C-19 | Proposed |
| DC-12 | After a framework fix the fingerprint did not change; needed `fresh_run` | Engine version in the fingerprint; a fix reruns tables automatically | Agree. Also put the effective config in the fingerprint (key limits, `information.yaml` patterns, abbreviations), or a config change has the same problem | C-41 | Proposed |

### 5A.3 P2 Documents and scope

| Id | Problem seen | Proposed change | Review comment | Related | Status |
|---|---|---|---|---|---|
| DC-13 | Many DPOF documents are "proposed" models, not client truth | `authority` field in triage: client truth, proposed, team. It sets the evidence weight | Agree. V1.1 already had a numeric document authority (AGENTS.md §5, "authority <= 3"); reuse that scale instead of a second one. A "proposed" document alone must never corroborate | C-25, R-03 | Proposed |
| DC-14 | CP1 client questions should be checked against documents first, done by hand | Open questions are an automatic input to P2.1c and P2.2; the reading plan starts with them | Agree | C-26, C-27 | Proposed |
| DC-15 | P2.2 / P2.3 order | Run the comparison (P2.2) before scope cards (P2.3) | Agree; same as F-01 | F-01, C-27 | Proposed |

### 5A.4 P3 to P6

| Id | Problem seen | Proposed change | Review comment | Related | Status |
|---|---|---|---|---|---|
| DC-16 | P3 output format not fixed for P4 | Build the STTM slot with a stub before P3 (plan step 10) | Agree. Write the interface as a JSON Schema so the team generator is checked against it when it arrives | C-34, F-03 | Proposed |
| DC-17 | Later-phase problems found late | Test that runs P1 to P6 on a very small test source after each framework change (plan step 13) | Agree. This also gives the demo source of F-04 | F-04, F-05 | Proposed |

### 5A.5 Approvals

| Id | Problem seen | Proposed change | Review comment | Related | Status |
|---|---|---|---|---|---|
| DC-18 | Decisions recorded from chat "under my name" are correct but not easy to see | Show `how=chat` on the gate page. The person must open the gate notebook to approve (already true); keep it as a rule | Agree, and go one step further: a chat-recorded decision is written **by the agent**, so it is a proposal until the person confirms it in the gate. This is the R-02 risk in practice | R-02 | Proposed |

### 5A.6 Priority

Owner proposal: DC-01 to DC-04 first (main causes of wrong state and repeated work).
Review proposal, in this order:
1. **DC-02** write guard (live data was overwritten)
2. **R-01** personal data before classification, and **R-02** with DC-18 (still open, not in the owner list)
3. **DC-03** stable open-point ids, **DC-01** single status record
4. **DC-04** raw reply first, **DC-05** root source
5. DC-12 fingerprint, DC-15 order, DC-16 and DC-17 (STTM interface + end-to-end test)

Note: S01_dpof is a real source, so step 11 work has started before step 13 (see F-05).

---

## 5B. Databricks-specific advice from Genie Code (input I-05)

Advice from Genie Code to the framework developer, from the V1.3 work on S01_dpof and its own operating limits. No new checks were run; items marked **check** must be tested before building on them.

### 5B.1 Facts learned about the environment

| Fact | Source | Affects |
|---|---|---|
| Project state is YAML/CSV/JSONL workspace files, written by several chats and notebooks. The `sources.yaml` overwrite was undone only from a `/tmp` copy | I-05 §1 | DC-01, DC-02 |
| Workspace files: no transactions, no row locks, weak version history | I-05 §1 | DC-09, DB-01 |
| Serverless: no `openpyxl` by default; sessions reset after long runs; `/Workspace` refuses `__pycache__`; no local Spark master | I-05 §2 | DC-06, tests |
| DPOF: 63 objects, 62 are views over two other schemas (MARS, DPOF_APP); one table has 99.1M rows; six tables are empty | I-05 §3 | C-17, DC-12 |
| Genie Code sees only tool output; long outputs are cut; sessions reset; Glean connector not in every session; **runs with the user's own permissions** | I-05 §4 | R-02, F-08 |
| P2.1a could not read 10 files: 9 images and 1 image-only PDF (IF-0043) | I-05 §5 | C-24 |
| Data root is in `/Workspace/Shared` | I-05 §7 | R-01 |

### 5B.2 Advice and review

| Id | Topic | Advice | Review comment | Related | Status |
|---|---|---|---|---|---|
| DB-01 | State | Human-readable files become views of the state. **Revisit D8:** one small Delta schema per project (`approvals`, `open_points`, `evidence`, `run_log`) for safe writes, history, `RESTORE`. Tools still export YAML/Markdown | Agree strongly. Solves DC-01 (one record), DC-09 (concurrency), and gives R-02 a proper store. Keep D8's real intent as "never write to bronze or prod". Generate ids with UUIDs or stable hashes (DC-03), not by counting rows, since Delta allows concurrent appends | D8, DC-01, DC-03, DC-09, R-02 | Proposed |
| DB-02 | State | **Revisit D2:** a Git folder gives diffs and a way back after a bad write; approval still without PRs | Agree. Git for framework code and exported views; Delta for state (DB-01). Do not depend on Git for approvals | D2, DC-02 | Proposed |
| DB-03 | Compute | Build for serverless (Spark Connect) first: no `sparkContext`, RDDs or JVM calls in the engine | Agree. Add a test that fails on these calls (static check of imports and attribute use) | C-09 | Proposed |
| DB-04 | Compute | Libraries in the serverless environment of each notebook or job, not installed per notebook | Agree; replaces the install part of DC-06. Pin versions | DC-06 | Proposed |
| DB-05 | Compute | Long work (P1.2 to P1.4 on up to 1000 tables) as a job with a `for_each` task: retry, timeout, run history. Notebooks show results and gates only | Agree. Reduces the need for the 25-minute budget (C-08) but keep per-table resume, so a retry does not redo finished tables. Cap `for_each` concurrency to protect the warehouse/cluster | C-07, C-08 | Proposed |
| DB-06 | Compute | Run the test suite as a job on a temporary copy, not from `/Workspace` | Agree; together with DC-02 this stops tests touching live state | DC-02 | Proposed |
| DB-07 | Bronze | Views have no Delta version: fingerprint = base table Delta version (`DESCRIBE HISTORY`) + view text | Agree; extends DC-12. Resolve views over views down to every base table; a view that joins several tables needs all their versions | DC-12 | Proposed |
| DB-08 | Bronze | View-to-table links from UC lineage (`system.access.table_lineage`) and from view text. Lineage also shows jobs that write base tables (answers "are empty tables loaded later?", Q-0003). **Check** system tables are enabled | Agree. Lineage only covers reads and writes through UC and has limited retention, so treat "no writer found" as unknown, not as "never loaded" | C-17, Q-07 | Proposed — check |
| DB-09 | Bronze | **Check** the fixed-seed sample gives the same rows through a view and its base table. A hash-based sample on the key columns always gives the same rows | Agree with the check. Note: key columns are not known before S2; hash on declared PK if any, else on all columns. If the base table has row filters or masks, the view and the base table can return different rows: profile what silver will read | C-18, C-19 | Proposed — check |
| DB-10 | Bronze | Read UC metadata first (comments, tags, declared PKs, statistics) | Agree; V1.1 already does this. Keep it in V1.3 | C-17 | Proposed |
| DB-11 | Bronze | Read each base table once: two views on the same base table (`pub_mschd`, `pub_msched`) need no two full scans | Agree when both views are plain projections. If a view filters or computes columns, profile its own output | C-17, C-18 | Proposed |
| DB-12 | Security | Data root in `/Workspace/Shared`, readable by all users by default. Check and limit access rights; keep `core.redact_values` on by default; silver privacy with UC column masks and row filters, set by tags | **Act now**: this is a current exposure, not a design item. Move the data root out of `Shared` or set ACLs to the project group. Then confirm what is already in the files (R-01) | R-01 | Proposed — **urgent** |
| DB-13 | Documents | `ai_parse_document` reads image-only PDFs and pictures from a UC volume; conflicts with D8, decide on purpose | Agree to decide on purpose. If DB-01 revises D8, a volume fits. Images can hold personal data, so parsed text goes through the same redaction | D8, C-24, R-01 | Proposed — decision |
| DB-14 | Documents | Client inbox read-only: a read-only volume for the team does this better than workspace folder permissions | Agree; same decision as DB-13 | D8 | Proposed — decision |
| DB-15 | Build | Codegen produces Lakeflow Spark Declarative Pipelines (SDP): expectations for P5.2 QA rules; `AUTO CDC` for SCD2 and "latest load version per key" | Agree in direction; it changes the P5 contract, so decide before DC-16/step 10. Limits: expectations cover row-level rules only; FK orphans, reconciliation and cross-source survivorship still need `lib/` checks and the master build | C-36, C-38, DC-16 | Proposed — decision |
| DB-16 | Build | Keep publishing informational PK/FK, comments and tags to UC | Agree; already V1.1 | C-38 | Keep |
| DB-17 | Build | Look at Data Quality Monitoring for S4 before building `lib/quality_profile.py` | Agree; check cost and coverage first | C-36 | Proposed — check |
| DB-18 | Build | Metric views for shared KPIs on silver | Defer: KPIs are gold scope, not bronze-to-silver | — | Deferred |
| DB-19 | Packaging | Declarative Automation Bundle with dev and prod targets for framework, jobs, pipelines. One source = bundle variables, not a copied folder | Agree. Replaces `sources/_template` copies. Fits DB-05 and DB-15 | C-02, C-13 | Proposed |
| DB-20 | Packaging | Run each source job on a schedule or on bronze change, so the baseline stays fresh | Agree, after DB-07 fingerprints work, so unchanged tables are skipped. A changed baseline must make affected CP decisions stale (C-21), not silently update them | C-21, DB-07 | Proposed |

### 5B.3 Decisions to revisit

I-05 argues against two V1.3 decisions. They need an explicit new decision, not a silent change.

| Decision | Current | Pressure from | Proposal |
|---|---|---|---|
| D8 No writes to the catalog | no scratch schema or volume | DB-01, DB-13, DB-14 | Narrow D8 to "never write to bronze or prod". Allow one project schema (state) and one volume (read-only inbox, document parsing) |
| D2 No Git for now | workspace folder | DB-02 | Git folder for code and exported views; approvals stay outside PRs |

### 5B.4 Priority

Genie Code proposes first: DB-01 (Delta state), DB-05 (jobs), DB-07 (base table fingerprints), DB-15 (SDP). Reason: they change the structure, so they cost more later.
Review agrees, and adds before them:
1. **DB-12** limit access on the data root (current exposure).
2. Decide **D8** and **D2** (5B.3), since DB-01, DB-13, DB-14 depend on them.
3. Decide **DB-15** before plan step 10 (STTM slot, DC-16), since the build target shapes the STTM interface.

---

## 6. Strengths (keep)

- Bronze-first order. Matches the existing rule "bronze wins for structure, documents win for meaning".
- Code/data separation with `data_root` and `x_layout.py`, with backward-compatible folder names.
- CP1 as a decision per open point, with stale detection.
- Each cell checked by a different method; `Result:` notes from real output.
- Time budget with resume; 1000-table limit.
- One profiling engine; no catalog writes.
- Better key detection: CDC columns, audit exclusion, Glean-cited keys, `*_nm` fallback.
- Abbreviation-aware copy detection (`plt` / `plant`).

---

## 7. Open plan steps and questions

### 7.1 Plan steps not done (from owner)
| Step | What | Related |
|---|---|---|
| 7 | Questions and assumptions | C-06, C-29, R-03 |
| 8 | Review index | — |
| 9 | Journal and knowledge base | C-43 |
| 10 | STTM slot | C-34, F-03 |
| 11 | Migration of real sources | F-05 |
| 13 | Full verification in both layouts | F-05 |

### 7.2 Questions for the owner
| Id | Question | Status |
|---|---|---|
| Q-01 | Will the next public release use V1.x or continue 2.x numbering? | Open |
| Q-02 | Where do the V1.3 code and `PLAN_V1_3.md` live? Needed to verify R-01 to R-03 against code | Open |
| Q-03 | Does S1 already classify columns before writing frequent values (R-01)? I-05: `core.redact_values` exists, but the baseline report and profiles hold top values and key data. Is redaction on in the S01_dpof run? | Partly answered |
| Q-04 | Which identity runs agent code on Databricks, and can it write to the folder that holds `approvals.jsonl` (R-02)? | Answered (I-05): the user's own identity. R-02 revised |
| Q-05 | Is CP1 of S01_dpof approved (AP-0001) or not? CHANGELOG and HANDOVER.md disagree (DC-01) | Open |
| Q-06 | What was overwritten in `_project/sources.yaml` by the test, and was it restored (DC-02)? I-05: restored from a `/tmp` copy | Partly answered |
| Q-07 | Are UC system tables (lineage, audit) enabled in this workspace (DB-08, R-02)? | Open |
| Q-08 | Who can read `/Workspace/Shared/<data root>` today, and which files there hold top values or key data (DB-12, R-01)? | Open — urgent |

---

## 7A. V1.4 requirements (owner, input I-06)

The owner cannot give access to the V1.3 system. V1.4 is built here, from these requirements and the review above.

| Id | Requirement | Effect on earlier items |
|---|---|---|
| RQ-01 | **No temporary or project tables.** State lives only in JSON, Excel, and other workspace files | DB-01 (Delta state) not possible; D8 stays. Concurrency and history must come from file design (append-only logs, lock files, versioned snapshots) |
| RQ-02 | **Add a conceptual model step** between bronze profiling and documents, built from the ontology, with Mermaid diagrams | New phase; changes the P1 → P2 order |
| RQ-03 | **Understand the application first.** Bronze tables are the backend of ~30 applications. Find what happens in the system from a business view, and the dependencies. This is the base for the logical model and the silver design. Unknowns are marked "?" (not clear from tables or documents) and work proceeds | New step before/with RQ-02 |
| RQ-04 | **Keep moving; iterate.** Operator and client often do not know. Document what is known, as it is. Questions do not block until the STTM section. New input at any phase can send work back: rerun, add a schema, add a profile | Confirms C-06, C-29; extends feedback/rerun (X) |
| RQ-05 | **STTM is the handoff between two teams.** V1.4 covers team 1 only (intake → STTM). Team 2 (STTM → build, deploy) is out of scope for now | P5, P6 out of scope; DB-15, DB-19 deferred |
| RQ-06 | **Team 1 has two overlapping roles.** Experts: read tables, form the mental model of the application, the conceptual model, and the silver organisation. Analysts: documentation and profiling, probe corner cases, build the STTM. **I-09: one application is typically worked by one person; no maker-checker.** The roles are hats one worker wears | Outputs organised per hat; no permission split |
| RQ-07 | **Reuse existing assets in the system:** the bronze data profiler (reference notebook), STTM templates (Excel and JSON) | Profiler and STTM format are inputs, not built from nothing |
| RQ-08 | **Framework builder helper**, callable on demand, separate from the source work: when a new deterministic asset (notebook, format) arrives, it helps integrate it into the main framework | New tool/skill |
| RQ-09 | **Overlay on Genie Code. No long-running jobs from Genie.** Heavy work runs in notebooks, not in Genie, so that there is a clear audit trail | DB-05 (jobs) replaced by notebooks run by a person |

### 7A.1 Quiz answers (round 1)

| Id | Topic | Answer |
|---|---|---|
| QA-01 | Deliverable | Spec + working code in this repo, tested locally with a fake source; owner ports to the system |
| QA-02 | Existing assets (profiler notebook, STTM Excel/JSON) | Not brought here. Design **placeholder interfaces**; real assets plug in later through the helper (RQ-08) |
| QA-03 | Model step order | **Bronze and documents together**, plus Glean. Documents (PDF, Word, PPT) give flowcharts and workflows; both sources help the application and conceptual model |
| QA-04 | Glean use — **conceptual first, columns last** | 1. Ask conceptual questions: how systems depend on each other, what work happens. 2. Only after parsing and integrating the conceptual answers does the framework ask about specific columns. 3. The framework tries to understand columns itself; only when something does not make sense does it ask Glean about columns and relationships |
| QA-05 | Helper form | Genie skill (`@fw-integrate`): analyse the new asset, map it to the framework contract, write adapter + registry entry + test + change note for review |

### 7A.2 Quiz answers (round 2)

| Id | Topic | Answer |
|---|---|---|
| QA-06 | Human checkpoints | **Only one gate: the STTM handoff.** Everything before it is a living draft |
| QA-07 | Open questions at handoff | **Expert decides each** at the gate: "accept assumption" or "must answer" |
| QA-08 | Git and distribution | **Framework in Git, maintained by a few people** (owner and a small group). **Workers download the framework into their workspace and cannot commit to it.** For a worker, everything lives in the **project folder** only. Workers give feedback to maintainers. Workers may use the helper, but they hand the result to maintainers, who integrate it into core Git |
| QA-09 | Source unit | **One application** = one source, with one or more schemas and lookup schemas. Shared masters are modelled across applications |

Consequences:
- Two areas with different rules: **framework** (read-only for workers, versioned by maintainers) and **project folder** (all worker state, no Git). The project must record which framework version produced each output.
- Audit for workers comes from file design only: append-only logs, versioned snapshots, hashes (RQ-01).
- The helper has two modes: a worker mode that makes a **contribution package** for maintainers, and a maintainer mode that integrates it into core.
- R-02 changes: one gate means one approval to protect; separation of duties (approver ≠ operator) still applies.

### 7A.3 Quiz answers (round 3)

| Id | Topic | Answer |
|---|---|---|
| QA-10 | Helper in worker projects | **Project plug-in:** the worker can use the new asset now, in the project folder, marked "not in core". A contribution package goes to maintainers |
| QA-11 | Model levels (each with Mermaid) | **Application process model**, **conceptual model**, **logical silver model**, plus "Other" (not yet specified, see round 4). Cross-application landscape **not** selected |
| QA-12 | Expert reviews before STTM | **Yes, non-blocking:** an expert marks a model version "reviewed" with notes; recorded for audit, shown at the STTM gate, never stops work |
| QA-13 | Framework upgrades | **Pin + guided upgrade:** each project pins a framework version; upgrade shows what changed and which outputs become stale, reruns only those |

### 7A.4 Quiz answers (round 4)

| Id | Topic | Answer |
|---|---|---|
| QA-14 | Fourth model level ("Other") | **App dependencies:** direct upstream and downstream systems of this one app (not the full landscape) |
| QA-15 | Glean channel | **Request/reply files:** framework writes question rounds as JSON; Genie sends through the connector when present, else a person pastes. Raw reply saved first (DC-04) |
| QA-16 | Review view | **One HTML page per app:** rendered Mermaid, open "?" items, assumptions, evidence links, review instructions; plus Excel with full lists |
| QA-17 | Milestone 1 | **Spine end to end:** project folder layout, state files and logs, each step from bronze baseline to STTM stub on a fake app. Thin first, deepen later |

### 7A.5 V1.4 shape (from RQ and QA, to confirm in the design spec)

- **Two areas:** framework (Git, maintainers only, pinned version per project) and project folder (all worker state; JSON/Excel; append-only logs; snapshots with hashes).
- **Source = one application** (one or more schemas + lookups).
- **Flow, team 1 only:** register app → bronze baseline (notebooks run by a person; Genie reads JSON summaries) → application understanding (bronze + documents + Glean conceptual rounds) → models: app dependencies, process model, conceptual model, logical silver model (Mermaid, "?" for unknowns) → column understanding (Glean column rounds only for what stays unclear) → STTM (placeholder template interface) → **STTM gate** (only gate; expert decides each open question; approver ≠ operator).
- **Never blocked before the STTM gate.** Any input at any time can send work back; fingerprints mark stale outputs; targeted reruns.
- **Expert reviews** of model versions: recorded, non-blocking, shown at the gate.
- **`@fw-integrate`:** worker mode (project plug-in + contribution package) and maintainer mode (integrate into core). Real profiler and STTM templates arrive this way.
- **Per-app HTML review page** + Excel.
- **Carried from the review:** R-01 redaction before any write, DC-02 test write guard, DC-03 stable ids, DC-04 raw reply first, DC-05 root source, DC-12/DB-07 fingerprints with engine version, config and view text.

---

## 8. Input log

Source images are kept in [`V1_3_review_inputs/`](V1_3_review_inputs/), named `<input id>_<topic>.png`.

| Id | Date | Input | Source | Effect |
|---|---|---|---|---|
| I-01 | 2026-11-13 | Cloned public repo 2.4.0; read README and AGENTS.md (tests not run: blocked) | — | Baseline = V1.1 |
| I-02 | 2026-11-13 | Owner: V1.1 vs V1.3 comparison table | [table](V1_3_review_inputs/I-02_v11_vs_v13_table.png) | Section 1; first review |
| I-03 | 2026-11-13 | Owner: phase-by-phase change list with statuses (STE format) | [P0–P1](V1_3_review_inputs/I-03_changes_p0_p1.png), [P2–X](V1_3_review_inputs/I-03_changes_p2_x.png), [open steps](V1_3_review_inputs/I-03_open_steps.png) | Sections 3–7 |
| I-04 | 2026-11-13 | Owner: design change proposals from S01_dpof work (other session, from saved notes, CHANGELOG, plan; code not run) | [part 1](V1_3_review_inputs/I-04_design_changes_1.png), [part 2](V1_3_review_inputs/I-04_design_changes_2.png) | Section 5A; Q-05, Q-06 |
| I-05 | 2026-11-13 | Genie Code: Databricks-specific advice to the framework developer (from S01_dpof work; no new checks run) | [part 1](V1_3_review_inputs/I-05_databricks_advice_1.png), [part 2](V1_3_review_inputs/I-05_databricks_advice_2.png), [part 3](V1_3_review_inputs/I-05_databricks_advice_3.png) | Section 5B; R-01 raised, R-02 revised; Q-03, Q-04, Q-06 updated; Q-07, Q-08 added |
| I-06 | 2026-11-13 | Owner: V1.4 requirements (typed); no access to the V1.3 system | — | Section 7A (RQ-01 to RQ-09) |
| I-07 | 2026-11-13 | Quiz rounds 1–4 | — | Section 7A.1–7A.5 (QA-01 to QA-17) |
| I-08 | 2026-11-13 | Owner: "go ahead" with the design spec | — | [`V1_4_DESIGN.md`](V1_4_DESIGN.md) drafted for review |
| I-09 | 2026-11-13 | Owner: the worker is typically one person; no maker-checker | — | V1_4_DESIGN §2, §4, §12, §18, §20, §21, §22 (K-07) updated; R-02 → accepted risk; RQ-06 clarified |
| I-10 | 2026-11-13 | Owner: explicit approvals at specific places, given in the chat with the user's name, no file edits; versions of JSON and other files kept through file names after reruns and feedback | — | V1_4_DESIGN: approval points AP-1 to AP-5 and chat protocol (§12, rewritten), versioned write-once file names (§7.5), §2, §4, §5, §6, §7, §8, §17, §18, §20, §21 updated; gate notebook removed |
| I-11 | 2026-11-13 | Owner: (1) new skill: HTML view of mappings and connections (entities, tables, ids, 1:N / N:1), non-overlapping boxes, correct text contrast, must match Mermaid (Mermaid is the accountability record); (2) approval of the logical silver model is needed before the STTM; (3) asked where else approvals are needed | — | V1_4_DESIGN §9.5 mapping model, §9.6 model viewer `@x-model-view` with `check-views`; AP-4 now blocks P8; §12.1 proposed AP-3S and project points AP-P1 to AP-P4 with chain rule; M1.8b; D-14.9, D-14.11; K-08 |
| I-12 | 2026-11-13 | Owner: approval statement must not be harsh — just name and milestone; the prompt shows the template to approve | — | V1_4_DESIGN §12.2 (template in chat; `I, <name>, approve AP-4.`; AP-5 template pre-fills decisions), §4, §12.5, M1.8; D-14.10 decided |
| I-13 | 2026-11-13 | Owner: the statement also carries the file version | — | V1_4_DESIGN §12.2: `I, <name>, approve AP-4 logical.v004.`; main file version(s) per point; version must match the request; §4, M1.8, D-14.10 |
| I-14 | 2026-11-13 | Owner: "go ahead", rest of the proposals accepted (D-14.1, D-14.2, D-14.5, D-14.6, D-14.9, D-14.11 defaults) | — | Milestone 1 built in `framework/` on branch `v1.4` (104 tests); build notes in V1_4_DESIGN §23 |
| I-15 | 2026-11-13 | Owner: the original major sequence stays; V1.4 upgrades what is inside it. Focus is the current work up to the STTM; not a completely new framework. Quiz: V1.3 sequence; new application-understanding + models step inside P2 (P2.2b), logical model inside P3; relabel code in place + port guide | — | Code relabelled to P1, P2.1, P2.2, P2.2b, P2.3, P3, P4.1 and CP1–CP4; V1.3 folders `work/P1…P4`, `review/`, `state/`; skills renamed; V1_4_DESIGN §0 mapping; new `V1_4_PORT_GUIDE.md`; 104 tests pass |
| I-16 | 2026-11-13 | Owner: notebooks and everything are orchestrated by the agent; first use integrates the client's assets with the integrate skill; clean up the repo and make it one system — the whole framework | — | Repo restructured (V1.4 at the root, 2.4.0 tools/sources/registry removed, kept in git history); `@b2s-run`, `@p0-setup`, `@p1-baseline`; notebook plug-ins (profiler) with run_plan/collect; `run_by` in events; P5/P6 ported; README, CHANGELOG, CONTRIBUTING, CI rewritten |
