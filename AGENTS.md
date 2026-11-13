# Bronze-to-Silver V1.4 — rules for Genie Code

You run this framework for the worker: every step, notebooks included. The worker gives input and approves
checkpoints CP1–CP4 in the chat. The V1.3 sequence is kept. Start with `@b2s-run`; no project yet → `@p0-setup`.
Design: `docs/V1_4_DESIGN.md`. Details: `rules/*.md`. Steps: `skills/` (use `@skill-name`).
Status of an application: `python -m b2s --project <folder> status <app>`.

## Must-follow rules
1. **One application per chat.** Write findings to files; a new chat must continue from the files alone.
2. **Read summaries, not data.** Never read a whole bronze table. Heavy work runs in the notebooks you start (`run_by = genie`), never in the chat.
3. **Never write a value of a sensitive column** (personal data, secrets, log values, free text) to any file. See `rules/privacy.md`.
4. **Checkpoints are the worker's, in the chat.** `approve request`, show the template, record the reply **exactly as typed**. Never write, complete or rephrase a statement; "OK" or silence is not an approval. CP5 and CP6 are automatic (`cp-auto`). See `rules/approvals.md`.
5. **Never overwrite a version file** (`*.vNNN.*`). Save changes with `python -m b2s save ... --reason "..." --via genie`. See `rules/files-and-versions.md`.
6. **Mark what you do not know, then continue.** `assumed` needs an `A-` item; `unknown` a `Q-` item. Questions never block before the STTM; P4 starts only after CP3.
7. **Never invent** an object, relationship, rule, code value or column meaning. Propose a change request (`CR-`) or ask.
8. **Glean: conceptual first**, columns only when `b2s columns` marks them `unclear`; save the raw reply first. See `rules/glean.md`.
9. **Do not edit framework files.** The client's notebooks and templates come in through `@fw-integrate`.
10. **Run `python -m b2s check <app>` after each change.** Fix all problems before you say the work is done.

## Sequence (V1.3)
| Step | What | Skill |
|---|---|---|
| P0 | Project, first-use integration of the client's assets, register application | `@p0-setup`, `@fw-integrate` |
| P1 → CP1 | Bronze baseline (runs `nb_p1_baseline`), open points, Glean check | `@p1-baseline` |
| P2.1 | Documents (runs `nb_p2_documents`), triage, evidence | `@p2-1-triage` |
| P2.2 | Documents compared with the baseline | `@p2-2-compare` |
| P2.2b | Application understanding; dependencies, process, conceptual models | `@p2-2b-understand` |
| P2.3, P2.4 → CP2 | Scope, privacy, column meanings; questions and assumptions | `@p2-3-scope` |
| P3 → CP3 | Central model: logical silver model (required before P4) | `@p3-logical` |
| P4 → CP4 → H1 | STTM: draft, validate, review, export | `@p4-sttm` |
| P5.1, P5.4 | PySpark notebooks from the STTM; shared master builds (dev only) | `@p5-1-codegen`, `@p5-4-masters` |
| P5.2, P5.3 → CP5 | QA on dev silver (runs `nb_p5_qa`); code review in a new chat; automatic CP5 | `@p5-2-qa`, `@p5-3-code-review` |
| P6.1 → CP6 → H2 | Readiness package; automatic CP6; handoff to deployment | `@p6-1-release` |
| Any time | Input from the worker, reruns | `@x-input` |
| Helpers | Checkpoints, Glean, model views | `@x-approve`, `@x-research`, `@x-model-view` |

Chain: each checkpoint needs the previous one for the versions it was made from.

## Vocabulary
- **Version file:** `<name>.vNNN.<ext>`, written once; its `.meta.json` names the input versions.
- **Folders:** `inbox/`, `work/P1…P6/`, `review/`, `state/`, `handoff/`.
- **Stale:** an input or setting changed after the output was made; `b2s status` says why and what to rerun.
- **Status:** known | assumed (`A-`) | unknown (`Q-`, shown `?`). Columns: known | inferred | unclear.
- **Items:** `E-` evidence, `Q-` question, `A-` assumption, `IN-` input, `CR-` change request, `IF-` document, `OP-` open point, `APR-` approval.
