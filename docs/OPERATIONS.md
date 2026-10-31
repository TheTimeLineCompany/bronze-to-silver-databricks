# Operations guide: set up and daily use

## Set up (P0, one time)
1. Put this folder in a Git repo. Add it to Databricks as a **Git folder** (Workspace -> Create -> Git folder).
2. GitHub: `.github/` is ready. Turn on branch protection for `main`: required check `pr-checks`, required reviews from code owners. Copy `.github/CODEOWNERS.example` to `.github/CODEOWNERS` and replace the team names.
3. **Register the skills** - every team member, once: Genie Code -> Settings -> **Add folder** -> `<Git folder>/skills`.
4. Replace the placeholders in `standards/` with the client's naming, coding, and QA guidelines (one `lib/qa_checks.py` function per QA item).
5. Agree `registry/ontology/business.yaml` with the client (objects, synonyms, abbreviations, relationships, rules).
6. Add each source: in `00_start_here` use action `new-source` (it copies `sources/_template/` and registers the source). Put the dump in `sources/<id>/00_inbox/` as it is.
7. Unity Catalog grants: phase 1 = read-only on bronze; phase 2 = write only to the dev silver schema.
8. Check: open `00_start_here`, set **action** to `setup-check`, click **Run all**. It must print `SETUP OK`.

## Daily use (one source per chat)
| Step | In Genie Code | Result (phase folder) | Checkpoint |
|---|---|---|---|
| P1.1-1.3 | `@p1-1-inventory`, `@p1-2-triage`, `@p1-3-source-brief` | `01_intake/` | **CP1** |
| P2.1 | `@p2-1-doc-profiles` | client profiling in one table | |
| P2.2 | `@p2-2-bronze-discovery` (then one new chat per card) | roles, grain, links, ontology map | |
| P2.3 | `@p2-3-evidence-reconcile` | `02_evidence/` | **CP2** |
| P3.1 | `@p3-1-entity-model` | change requests, `registry/` | **CP3, CP3b** (global) |
| P4.1-4.4 | `@p4-1-sttm-author`, `@p4-2-sttm-validate`, new chat `@p4-3-sttm-review`, `@p4-4-sttm-export` | `04_mapping/` | **CP4, CP4b** -> **H1** |
| P5.1-5.3 | `@p5-1-pyspark-codegen`, `@p5-2-qa-runner`, new chat `@p5-3-code-review` | `05_build/` | **CP5** |
| P6.1 | `@p6-1-handoff-package` | `06_handoff/` | **CP6** -> **H2** |
| any | `@x-clarify` | questions at each kickoff and on each new input; answers routed | any |
| any | `@x-feedback-rerun` | feedback, upstream issues, rerun | any |

At each checkpoint the reviewer opens `<phase folder>/checkpoint/<CP>.html`.
Your input, any time: in `00_start_here` use `give-instruction`, `give-feedback`, or `register-uploads`. Each input is checked against
the three ontology layers, and Genie asks only the questions that matter (`@x-clarify`) before it works.
Detailed feedback: `python tools/x_feedback.py new <id> <CP> --comment "..." [--include ...] [--data-table ... --data-filter ...]`.

The example sources, documents, bronze data, and entities are **fictional**.
