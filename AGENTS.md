# Silver modelling project - rules for Genie Code

Genie Code reads this file automatically for every notebook and file in this repo.
These rules apply always. The steps for each task are in the skills under `skills/` (use `@skill-name`).
Picture of the whole process: `docs/process_map.html`. Status and next step of a source: `python tools/x_navigator.py <source>` (people use the notebook `00_start_here`).

## 1. Goal
Move about 30 supply-chain source systems from bronze to silver in Unity Catalog.
Silver must have clear business objects, primary and foreign keys, and line-level integrity.

- **Phase 1** (modelling team): source dump + bronze profiling -> central model + one STTM per source.
- **Phase 2** (engineering team): approved STTM -> PySpark notebooks + Jobs that follow `standards/`.
- **Deployment team** receives the package after CP6.

## 2. Phases, checkpoints, handovers
| Phase | Name | Scope | Skills | Checkpoint (human) | Approver |
|---|---|---|---|---|---|
| P0 | Setup | once | (README) | - | project lead |
| P1 | Intake and focus | per source | p1-1, p1-2, p1-3 | CP1_source_brief | phase1-lead |
| P2 | Discovery and evidence | per source | p2-1, p2-2, p2-3 | CP2_evidence | phase1-lead |
| P3 | Central model | global | p3-1 | CP3_central_model, CP3b_key_rules | data-architect |
| P4 | Mapping | per source | p4-1, p4-2, p4-3, p4-4 | CP4_sttm, CP4b_business_logic | phase1-lead, client-sme |
| P5 | Build | per source | p5-1, p5-2, p5-3 | CP5_code_qa | phase2-lead |
| P6 | Handoff | per source | p6-1 | CP6_handoff | deployment-lead |
| X | Feedback and rerun | any | x-feedback-rerun | (any checkpoint) | the reviewer |

- **H1** (phase 1 -> phase 2) after CP4 and CP4b: `04_mapping/` (approved STTM, exports, reviews, checkpoint packs) + `02_evidence/evidence_register.csv`.
- **H2** (phase 2 -> deployment) after CP6: `05_build/` (notebooks, job, QA), `06_handoff/readiness.md`, `04_mapping/exports/`.
- Status lives in `registry/sources.yaml`. `tools/x_validate_gate.py` checks order, evidence, feedback, upstream issues, and fresh checkpoint packs on every PR.
- **You (Genie Code) never set a checkpoint to approved and never set feedback to verified.** You prepare the evidence. A person approves in the PR.
- **Checkpoint pack.** The last step of each phase runs `python tools/x_checkpoint_pack.py <id> <CP>` (global: `global --all`). It writes `<phase folder>/checkpoint/<CP>.html` (one page for the reviewer), `.xlsx` (all lists), `.json` (for the next skill or a table), and `.md` (summary). Run it again after every change; a stale pack blocks approval.

## 3. Folder layout (folder number = phase number)
| Path | What it holds | Who changes it |
|---|---|---|
| `registry/ontology/` | business, data, and information ontology | change request (P3) / project lead |
| `registry/entities.yaml`, `key_normalisation.yaml` | shared masters, key rules | change request (P3) |
| `registry/sources.yaml` | sources, business scope, checkpoint status | status only by approved PR |
| `registry/open_questions.yaml`, `decisions.md` | questions, decisions | anyone adds |
| `registry/feedback/`, `checkpoint/`, `board/` | global feedback, CP3 packs, feedback board | reviewers / code |
| `sources/<id>/00_inbox/` | the raw dump | read only - never edit |
| `sources/<id>/01_intake/` | manifest, triage, source brief (P1) | p1-1, p1-2, p1-3 |
| `sources/<id>/02_evidence/` | evidence register, `profiling/`, `discovery/` (P2) | p2-1, p2-2, p2-3 |
| `sources/<id>/04_mapping/` | `sttm.yaml` (truth), `exports/`, `reviews/` (P4) | p4-x, reviewers |
| `sources/<id>/05_build/` | notebooks, job, `qa_results/`, `reviews/` (P5) | phase 2 |
| `sources/<id>/06_handoff/` | `readiness.md` (P6) | phase 2 |
| `sources/<id>/<phase>/checkpoint/` | checkpoint pack | `tools/x_checkpoint_pack.py` |
| `sources/<id>/<phase>/feedback/<CP>/` | feedback items, upstream issues, attachments | reviewers, agents |
| `sources/_template/` | empty folder set with READMEs for a new source | project lead |
| `masters/<master table>/` | build notebook + QA of each shared master (survivorship across sources) | `tools/p5_4_gen_master_build.py` |
| `standards/`, `lib/`, `tools/`, `schemas/`, `tests/` | client standards (incl. QA checklist), shared code, scripts | owners, by PR |
| `.github/` | PR checks, CODEOWNERS, PR template | project lead |
Each phase folder has a `README.md` that lists its files, who writes them, and who reads them.

## 4. Focus: never drown in the dump
The inbox can hold hundreds of files. Work as a funnel:
1. **Inventory first** (p1-1): a script lists files, duplicates, and versions. You read only `01_intake/manifest.md`.
2. **Triage** (p1-2): each file is core / supporting / background / ignore. Core files are limited to `budgets.max_core_files` (15). Each core and supporting file has a `read_plan` (sheets, pages, sections).
3. **Read only the read plan** (p1-3). Write facts as short claims in `02_evidence/evidence_register.csv` (E-0001 ...).
4. **After P1, never read `00_inbox` again.** Later steps read `source_brief.md` and the evidence register. If a fact is missing, add it as new evidence (P2.3) or ask for feedback with `include_paths`.
5. Excel profiling workbooks are read by a script (p2-1), not by you. Use `doc_profiles.csv` by filter.
6. **Bronze is profiled by code, not by you** (p2-2). Code reads Unity Catalog metadata and lineage first, then works on samples and runs exact checks only for key and link candidates, within `discovery_budgets`. You read `02_evidence/discovery/summary.md` and answer one card per chat. Never `SELECT *` a whole table.
7. The brief stays under `budgets.source_brief_max_words` (1800). One claim stays under 40 words.
8. Old versions, copies, and drafts are `ignore`. Emails and minutes are `background` unless feedback points to them.

## 5. Confidence and evidence
| Level | Meaning |
|---|---|
| high | usable alone, unless bronze contradicts it |
| medium | needs one corroboration: bronze profiling, or a second document with authority <= 3 |
| low / unknown | a hypothesis only; verify in bronze or ask the client |

- **Bronze wins for structure** (keys, nulls, formats, cardinality). **Documents win for meaning** (definitions, rules, code values). A client answer wins for both.
- A PK, BK, FK, or business-logic column cannot rest only on low or unknown evidence. The validator checks this.
- Evidence status: unverified -> corroborated / confirmed_by_bronze, or contradicted / superseded.
- Conflicts: bronze contradicts a document -> mark `contradicted`, add the bronze fact, raise a question for meaning.

## 6. Ontology: one chain from business to bronze
Every silver column must trace back through an unbroken chain:
**business object** (business.yaml) -> **silver table + data class** (data.yaml) -> **silver column** -> **bronze column** -> **evidence** (E-xxxx) -> **origin** (IF-xxxx + location, `02_evidence/discovery/` or `profiling/` file, or answered question).
1. Use the business object NAME, not the source's word. Source words go into `synonyms`.
2. Each target table states `business_object` and `data_class`. The load pattern must be allowed for the class.
3. Shared masters use a conformed class (master, reference) and match `registry/entities.yaml`.
4. Each FK follows a relationship in `business.yaml`.
5. Each business-logic column names a business rule (`BR-<DOM>-<nnn>`) and needs CP4b.
6. Never invent an object, relationship, or rule. Propose it by change request (`@p3-1-entity-model`).
7. `python tools/x_ontology_check.py` must print `ONTOLOGY COHERENT`.

## 7. Golden rules
1. **Evidence for every mapping.** Each non-technical STTM column cites `provenance.evidence` ids. No evidence -> `confidence: low` + question.
2. **Do not invent** tables, columns, codes, rules, or objects.
3. **Keys use the registry.** `rule: normalised_key` with a `key_rule`; in code `lib/keys.normalise`. Never write your own trim/upper/lpad for keys.
4. **FKs point to a surrogate key**: of a shared master (`fk.entity`) or of another table in the same STTM (`fk.table`), with cardinality, orphan policy, and `fk.lookup_on` (one expression per parent business-key column; required for composite keys).
5. **Registry and ontology changes are change requests.** Never edit them silently.
6. **YAML is the truth.** Change `04_mapping/sttm.yaml`, then regenerate exports. Never edit `exports/`.
7. **Run the checks** after every change: `p1_2_check_context.py`, `p4_2_validate_sttm.py`, `x_ontology_check.py`, `x_validate_gate.py`. Fix all errors before you say the work is done.
8. **Blocking questions stop STTM approval and CP6.** Continue other work; do not hide the question.
9. **Phase 2 follows `standards/`** and reuses `lib/`. The STTM is the contract; do not "fix" the mapping in code.
10. **Dev only.** Never write to prod schemas. Read-only on bronze.
11. **Shared masters are never written by a source notebook.** A source writes its staging table (`slv_stg_mst_<name>_<code>`); the master build in `masters/` applies the survivorship rules (`key_normalisation.yaml`, CP3b) and seeds the unknown member (`lib.keys.UNKNOWN_SK`). An entity mapped by two or more sources needs survivorship rules.
12. **Scope and privacy come from discovery.** A table with scope `out_of_scope` or `derive_instead` (application logs, audit trails, staging, aggregates) and a column with scope `out_of_scope` (login times, session ids, tokens) do not go to silver without a `scope_override` with a reason. A `secret_or_token` column never goes to silver. A personal-data column (name, email, phone, address of a buyer, supplier, or contact) needs `privacy: {class, handling: keep_tagged | mask | hash, reason}`. Never copy sample values of personal data into any file.
13. **Generators are safe to re-run.** They keep TODO(genie) code and add `# REVIEW(STTM changed)` blocks when a spec changed; remove a REVIEW block only after you updated the code.

## 8. Feedback and rerun (any checkpoint)
A reviewer can give feedback in any mix of kinds: `comment`, `include_paths`, `ignore_paths`, `code`, `data` (table + filter), `attachments`, `answer`.
1. Before a step, run `python tools/x_feedback.py list <id> --open`. Apply open items for your checkpoint first.
2. `plan` -> `set in_progress` -> `reset` later checkpoints -> rerun the steps in `rerun_now` -> check `then_recheck`.
3. Use only the feedback content plus the step's normal inputs. Do not re-read the whole inbox.
4. `set applied` with a summary and changed files. Only the reviewer sets `verified` or `rejected`.
5. Open, in_progress, or applied feedback blocks its checkpoint.
6. Log every run: `python tools/x_feedback.py log <id> <step> ...` -> `run_log.jsonl`.
7. **Upstream issues.** When your step finds a problem that an earlier phase owns, do not work around it. Run `python tools/x_feedback.py raise <id> <earlier CP> --step <your skill> --comment "..." --blocks <your CP>`. A person accepts or rejects it. The same problem a third time (`--related`) stops the checkpoint: a person decides.
8. The board of all items: `python tools/x_checkpoint_pack.py board` -> `registry/board/`.
Details: `@x-feedback-rerun`.

## 8b. The person's input: typed, uploaded, and clarified
1. **Before every step, read the active instructions** for your step and for `all` in `sources/<id>/instructions.yaml` (IN-xxx), and the files they attach. They win over your defaults, but not over evidence from bronze: if they conflict, ask.
2. Typed feedback becomes a normal FB item. Uploaded files are registered from `sources/<id>/uploads/` as instruction, feedback, or handover (`<phase>/handover/`, passed to the next stage).
3. **Check every input against the ontology.** `python tools/x_input_ontology.py <id> <IN-/FB-id>` matches it to the business, data, and information layers and gives unknown names, new concepts, conflicts, intent, and route. Never act on an input you have not traced.
4. **Clarify first.** At the start of each checkpoint and after each new input, the navigator shows a clarify step. Run `@x-clarify`: ask at most 7 questions, ONLY about what the check could not settle (unknown, new, conflicting, unclear, or a rerun of approved work). Record the answers; the input then carries its route. Do not start the step's work while a clarify step is open, unless the person skips it.
5. "I don't know" becomes a client question. Never turn a guess into evidence. Team knowledge is evidence with origin `team_knowledge`, confidence medium.

## 9. How to work in chats
- **One source per chat.** Do not mix sources. **One discovery card per chat.**
- **Write findings to files.** A new chat must be able to continue from the files alone.
- **Reviews in a new chat** (`@p4-3-sttm-review`, `@p5-3-code-review`). Never review your own work in the same chat.
- **When stuck, ask.** Add a question with evidence and tell the user.

## 10. Skills (use `@skill-name`)
| Step | Skill | Main output |
|---|---|---|
| P1.1 | `@p1-1-inventory` | `01_intake/manifest.md` |
| P1.2 | `@p1-2-triage` | `01_intake/triage.yaml` (confirmed, read plans) |
| P1.3 | `@p1-3-source-brief` | `source_brief.md` + first evidence |
| P2.1 | `@p2-1-doc-profiles` | `02_evidence/profiling/doc_profiles.csv` |
| P2.2 | `@p2-2-bronze-discovery` | `02_evidence/discovery/` (roles, grain, links, ontology map, cards) |
| P2.3 | `@p2-3-evidence-reconcile` | evidence statuses, questions, updated brief |
| P3.1 | `@p3-1-entity-model` | change request, ontology + registry updates |
| P4.1 | `@p4-1-sttm-author` | `04_mapping/sttm.yaml` |
| P4.2 | `@p4-2-sttm-validate` | validator PASS |
| P4.3 | `@p4-3-sttm-review` (new chat) | `04_mapping/reviews/sttm_review.md` |
| P4.4 | `@p4-4-sttm-export` | `exports/sttm.xlsx`, `er.mmd` |
| P5.1 | `@p5-1-pyspark-codegen` | `05_build/nb_*.py`, job |
| P5.2 | `@p5-2-qa-runner` | `05_build/qa_results/summary.json` |
| P5.3 | `@p5-3-code-review` (new chat) | `05_build/reviews/code_review.md` |
| P6.1 | `@p6-1-handoff-package` | `06_handoff/readiness.md` |
| X | `@x-feedback-rerun` | `<phase>/feedback/<CP>/FB-xxxx.yaml`, rerun, upstream issues |
| X | `@x-clarify` | `<phase>/clarify/QZ-<CP>-nnn.md` + answers -> instructions, evidence, feedback, questions |

## 11. Vocabulary
- **Business object:** a thing the business talks about (Supplier, ShipmentLeg). Defined in `business.yaml`.
- **Data class:** how the object is stored (master, reference, event, agreement, measure, snapshot, bridge).
- **Grain:** what one row means, as one sentence.
- **Business key (BK):** natural identifier after normalisation. **Surrogate key (SK):** hash of BK (+ `effective_from` for SCD2).
- **Evidence (E-xxxx):** one short claim with origin, location, confidence, status.
- **Checkpoint (CPn):** human approval in a PR. **Handover (H1, H2):** a package that moves to the next team.
- **Feedback (FB-xxxx):** human input at a checkpoint that causes a rerun. **Upstream issue:** an FB item raised by an agent (status `proposed`).
- **Table role:** what a bronze table is: master, reference, transaction header/line, event, snapshot, bridge, aggregate, staging.
- **Card (T-xxx, R-xxx, D-001):** one discovery decision code could not make (table, related table outside the schema, documents vs bronze); one agent chat answers one card.
- **Scope:** in_scope, out_of_scope, derive_instead, review (a person decides), technical (load columns). Set per table and per column.
- **Column class:** what a column holds, from its name AND its values (for example key, business_attribute, application_log, audit_metadata, secret_or_token, personal_data, payload_or_free_text).
- **Instruction (IN-xxx):** a standing rule typed or uploaded by a person. **Clarify (QZ-...):** questions to the person before work starts.
