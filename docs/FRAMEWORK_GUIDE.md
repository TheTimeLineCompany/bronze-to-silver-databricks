# Framework guide: bronze to silver with Genie Code (v2)

Written in simple technical English (ASD-STE100 style). Visual version: `process_map.html` (same folder).

## 1. The problem
The client has about 30 supply-chain source systems in bronze. We must make a clean silver layer with clear business objects, keys, and line-level integrity.
- **Phase 1 team**: source dump + bronze -> central model + one source-to-target mapping (STTM) per source.
- **Phase 2 team**: approved STTM -> PySpark notebooks and Jobs that follow the client standards.
- **Deployment team**: takes the package to production.

Two extra difficulties:
1. Each source arrives as a **large dump** of mixed files: overviews, profiling workbooks with their own confidence levels, old versions, copies, emails. An agent that reads all of it gets lost and mixes old and new facts.
2. Thirty sources must give **one coherent model**, not thirty local ones.

## 2. The process in one picture
```
00_inbox (dump)
  P1 Intake & focus   p1-1 inventory (code) -> p1-2 triage -> p1-3 brief + evidence  ......... CP1
  P2 Discovery+evid.  p2-1 client profiling (code) -> p2-2 bronze discovery (code + cards) -> p2-3 reconcile CP2
  P3 Central model    p3-1 change requests -> ontology + registry (global) .................. CP3, CP3b
  P4 Mapping          p4-1 STTM -> p4-2 validate (code) -> p4-3 review (new chat) -> p4-4 export . CP4, CP4b
                                                                                 == H1 ==> phase 2
  P5 Build            p5-1 codegen -> p5-2 QA (code) -> p5-3 code review (new chat) ............ CP5
  P6 Handoff          p6-1 readiness package ............................................... CP6
                                                                                 == H2 ==> deployment
  X  Feedback         at any checkpoint: FB item -> plan -> reset -> rerun -> applied -> verified
     Upstream issue   a later step raises a 'proposed' item on an earlier checkpoint -> person accepts -> same loop
  Every checkpoint:   checkpoint pack in <phase folder>/checkpoint/  (.html for the reviewer, .xlsx, .json, .md)
```
Three kinds of work:
- **Agent** (Genie Code): reads the parts it is told to read, writes briefs, evidence, mappings, code, reviews.
- **Code** (scripts, PR checks): inventory, extraction, profiling, validation, QA, checkpoint rules. Code gives guarantees; a prompt cannot skip it.
- **Human**: decides triage when unsure, answers questions, gives feedback, approves each checkpoint in a PR.

## 3. Focus: the funnel against the dump
| Stage | Who | What gets smaller |
|---|---|---|
| Inventory | code | all files -> one manifest with duplicates and versions found |
| Triage | agent + human | manifest -> max 15 core files, each with a read plan |
| Read plan | agent | core files -> only named sheets, pages, sections |
| Evidence register | agent | text -> short claims (max 40 words) with origin and confidence |
| Source brief | agent | claims -> one page (max 1800 words) |
| Later phases | agent | read brief + register only; never the inbox again |

Budgets and rules are in `registry/ontology/information.yaml` and enforced by `tools/p1_2_check_context.py`.

## 3b. Bronze discovery: the biggest piece of P2
Goal: know what each bronze table is, with numbers as proof, without reading all data.
| Stage | Who | Output |
|---|---|---|
| Unity Catalog metadata and lineage (comments, tags, masks, declared keys, statistics, history, who writes and reads) | code, once, no data read | `metadata/`, `lineage_view.json` |
| catalog, profile (sample, value-kind ratios), keys (exact check on candidates only) | code, parallel per table | `columns.csv`, `keys.csv` |
| link candidates, containment of distinct values (raw and normalised) | code, parallel per batch | `links.csv` (FK, cardinality, "needs key rule") |
| roles, grain, lineage levels, derived tables, ontology mapping, shared code domains | code | `tables.csv`, `graph.json`, `bronze_er.mmd`, `summary.md` |
| table scope and column class/scope: application logs, audit, secrets, personal data (name + content + tags) | code; a person confirms at CP2 | `tables.csv`, `column_scope.csv` |
| wider search: related tables outside the schema, documents vs bronze, same object in other sources | code | `related.csv`, `doc_gaps.csv`, `overlap.csv` |
| decisions code cannot make | one agent per card (Genie Code chat, or the card runner on a serving endpoint) | `cards/T-, R-, D-xxx.result.yaml` |
| merge, upstream issues, evidence | code | final `tables.csv`, FB items, evidence lines |
Method: data-profiling literature (Abedjan, Golab, Naumann; HCA/DUCC, SPIDER; FK ranking) and Kimball's grain and table roles.
See `skills/p2-2-bronze-discovery/references/methods.md`. Budgets: `information.yaml` -> `discovery_budgets`.

Parallel work on Databricks: code tasks run as a Job with for-each tasks (`02_evidence/discovery/job.json`).
Genie Code has no documented sub-agents, so judgement goes on cards. A card is a self-contained task; any runtime can answer it:
a person, a Genie Code chat, `tools/discovery/card_runner.py` (one fresh LLM call per card, answers checked), or later a
Databricks multi-agent app / Agent Bricks supervisor that uses the card runner as a tool.

## 4. Confidence
Client profiling workbooks have their own confidence values (High/Medium/Low, percentages, colours). `p2-1` normalises them to high / medium / low / unknown.
- **high**: usable alone unless bronze contradicts it.
- **medium**: needs one corroboration (bronze, or a second strong document).
- **low / unknown**: hypothesis only. Verify in bronze or ask the client.
- **Bronze wins for structure, documents win for meaning, a client answer wins for both.**
- The STTM validator refuses a key, FK, or business-logic column that rests only on low/unknown evidence.

## 5. Ontology: three layers, one chain
| Layer | File | Answers |
|---|---|---|
| Business | `registry/ontology/business.yaml` | What does the business talk about? Domains, processes, business objects (+ synonyms), relationships, business rules |
| Data | `registry/ontology/data.yaml` | How is each object stored? Data classes (master, reference, event, agreement, measure, snapshot, bridge), load patterns, key types |
| Information | `registry/ontology/information.yaml` | Where does each fact come from and how far can we trust it? Document types, relevance, confidence, evidence status, phases, checkpoints |

The chain for every silver column:
`business object -> silver table + data class -> silver column -> bronze column -> evidence E-xxxx -> origin (file + location, bronze profile, or client answer)`.
`tools/p4_2_validate_sttm.py` checks each STTM against it. `tools/x_ontology_check.py` checks all files together.
Details: `registry/ontology/README.md`.

## 6. Checkpoints and handovers
| CP | Scope | Human approves | Code checks before approval |
|---|---|---|---|
| CP1_source_brief | source | triage and brief are right | every file triaged, budgets, read plans, brief cites existing evidence |
| CP2_evidence | source | evidence is enough and conflicts are handled | register well formed, bronze profiling results exist |
| CP3_central_model | global | business objects, entities, relationships | all entities approved, ontology coherent |
| CP3b_key_rules | global | key formats, survivorship | CP3 approved first |
| CP4_sttm | source | the mapping | validator PASS, STTM approved, review PASS, CP3/CP3b approved |
| CP4b_business_logic | source | client SME signs off formulas | sign-off file PASS; required when business_logic columns exist |
| CP5_code_qa | source | code matches STTM and standards | QA summary all pass, code review PASS |
| CP6_handoff | source | package is ready | exports, readiness file, no blocking questions |

For every checkpoint: earlier checkpoints approved, no feedback open / in_progress / applied, approver + date + PR filled in.
- **H1** after CP4 + CP4b: phase 1 -> phase 2.
- **H2** after CP6: phase 2 -> deployment.

## 6b. Checkpoint packs
At every checkpoint, `tools/x_checkpoint_pack.py` writes four files with the same content into `<phase folder>/checkpoint/`:
| File | For | Content |
|---|---|---|
| `<CP>.html` | reviewer | one page, no tabs: status, key numbers, connections, needs attention, reviewer decides, one key table |
| `<CP>.xlsx` | people and machines | README sheet + one sheet per list, filters on |
| `<CP>.json` | next skill, agents, a Delta table | everything above + SHA-1 of every input |
| `<CP>.md` | PR description, Git history | one-page summary |
The checkpoint check refuses an approval when the pack is missing or older than its inputs.

## 6c. Shared masters: survivorship
Many sources describe the same parts, suppliers, and buyers. No source writes a shared master directly:
1. Each source notebook writes its staging table `slv_stg_mst_<name>_<code>` (current state per business key).
2. The master build (`masters/<table>/`, made by `tools/p5_4_gen_master_build.py`) reads all staging tables of the entity,
   picks each attribute by the survivorship rules (`key_normalisation.yaml`, CP3b; a NULL never wins), records the winners
   in `_survivor`, loads the master (SCD2 or merge), and seeds the unknown member.
3. Job order: source notebooks of the entity -> master build -> process tables.

## 7. Feedback and rerun
A reviewer is not limited to approve / reject. At any checkpoint a reviewer writes one feedback item (`FB-xxxx.yaml`) with any mix of:
| Kind | Example |
|---|---|
| comment | "ETA text is local port time." |
| include_paths / ignore_paths | "Read 03_Workshops/", "Ignore Archive/" |
| code | a PySpark snippet for a cell or a transform |
| data | a table + filter (+ columns) to profile or test |
| attachments | a new file (for example a port time-zone list) |
| answer | the answer to an open question |

`tools/x_feedback.py plan` says which steps to rerun now, which to recheck, and which checkpoints go back to pending. The agent reruns only those steps, with only the feedback content plus the normal inputs, then marks the item `applied`. The reviewer marks it `verified` or `rejected`. Every run is logged in `run_log.jsonl`.

**Upstream issues.** A later step that finds a problem owned by an earlier phase (missing evidence, wrong grain, a new business object)
raises a `proposed` item on that earlier checkpoint, with `--blocks <its own checkpoint>`. A person accepts it (normal loop) or rejects it.
This replaces a free "scratchpad": every issue has an owner, a status, and a gate. A loop guard stops the third attempt for the same problem.
All items are on one board: `registry/board/feedback_board.html`.

## 7b. Your input: typed, uploaded, checked, clarified, routed
The process is interactive. Input can come at the start of a checkpoint or at a review, as text or as files.
1. **Capture** in `00_start_here`: `give-instruction` (a standing rule IN-xxx for one step or all), `give-feedback` (an FB item),
   or files in `sources/<id>/uploads/` + `register-uploads` with purpose instruction, feedback, or handover (copied to `<phase>/handover/` for the next stage).
2. **Check against the ontology** (`tools/x_input_ontology.py`, code): each term is matched to the business layer (objects, synonyms,
   abbreviations, relationships, business rules), the data layer (classes, load patterns, bronze and silver tables and columns), and
   the information layer (phases, steps, checkpoints, evidence, questions). It finds unknown names, new concepts, conflicts (with an
   instruction, strong evidence, a relationship's cardinality, a business rule), the intent, and the route (first step that must use it,
   checkpoints that go back to pending, change requests). For files it reads names, headers, and sheet names, never values.
3. **Clarify** (`@x-clarify`, one agent): at most 7 questions, only about what the check could not settle. A clear, known,
   conflict-free input gets none. The navigator shows this step first, at each kickoff and after each new input; `clarify-skip` records a skip.
4. **Route**: answers become instructions, evidence (`team_knowledge`, medium at most), feedback, client questions, or CP3 change requests.
   The input carries its route, so the right skill picks it up and the rerun starts at the right step.

## 8. Why it is built this way (lessons from the CCA-F exam)
| Lesson | How we use it |
|---|---|
| Rules that must always hold belong in code. | Validators, QA checks, and checkpoint rules run in the skill and again in the PR. |
| Prerequisite gates. | `x_validate_gate.py` blocks a checkpoint before its prerequisites, evidence, and feedback are done. |
| Always-on instructions in a project file. | `AGENTS.md` (read automatically, < 20,000 characters). |
| One job per skill, clear descriptions. | 16 numbered skills; call with `@name`. |
| Manage context; do not flood it. | Inventory -> triage -> read plans -> brief. One source per chat. Findings in files. |
| Keep provenance. | Every claim has an evidence id with origin and location. |
| Structured output with a schema. | STTM YAML + JSON Schema; nulls allowed instead of guesses. |
| Independent review. | Reviews run in a new chat. |
| Escalate missing information. | Questions with a blocking flag; feedback items. |
| Never hide a failure. | Profiler and QA report `error` when they cannot run; an error is never a pass. |
| Least privilege. | Read-only bronze for phase 1; dev-only writes for phase 2. |

## 9. How to roll out
1. **P0 setup** (`README.md`). Agree the business ontology with the client first.
2. **Pilot with two sources**: one master (buyers) and one event source (container moves). Go through every checkpoint, give real feedback.
3. **Tune** templates, budgets, synonyms, and standards.
4. **Wave 1**: master and reference sources -> stable central model (CP3, CP3b).
5. **Waves 2 to n**: process sources, about 5 per wave. Phase 1 starts the next wave while phase 2 builds the last one.

## 10. Rules for people
- Approve checkpoints only in pull requests.
- Give feedback as feedback items, not only in chat, so the rerun is traceable.
- Verify or reject each applied feedback item yourself.
- Answer questions in `registry/open_questions.yaml`.
- Test a changed skill in a new chat.

## 11. Limits and assumptions
- Genie Code has no documented hooks or sub-agents. Enforcement uses scripts, PR checks, CODEOWNERS, and Unity Catalog grants.
- We assume Genie Code agent mode can run the repo's Python scripts. If not, people run the same commands; the PR check still enforces them.
- The inventory reads page counts of PPTX, PDF, and DOCX only if those Python libraries exist.
- The examples (sources, documents, entities, key rules, naming) are fictional.
