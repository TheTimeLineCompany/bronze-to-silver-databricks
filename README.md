# Bronze-to-Silver Databricks

**An agent-run framework that moves the backend tables of many applications from the bronze layer to a modelled
silver layer on Databricks.** Genie Code runs the steps — notebooks included — and the worker gives input and
approves checkpoints in the chat. All project state is plain files in a workspace folder; no tables are needed.

Version: see [`FRAMEWORK_VERSION`](FRAMEWORK_VERSION) · Design: [`docs/V1_4_DESIGN.md`](docs/V1_4_DESIGN.md) ·
Changes: [`CHANGELOG.md`](CHANGELOG.md)

## The sequence
```
P0 Setup ─ P1 Bronze baseline ─(CP1)─ P2 Documents, application understanding, scope ─(CP2)─
           P3 Central model ─(CP3)─ P4 STTM ─(CP4)─ H1 ─ P5 Build and QA ─(CP5 auto)─ P6 Release ─(CP6 auto)─ H2
```

| Step | What happens | Run by | Skill |
|---|---|---|---|
| P0 | Project folder, framework pin; **first use: the client's own notebooks and templates are integrated** as plug-ins | agent | `@p0-setup`, `@fw-integrate` |
| P1 | Bronze baseline: inventory, column profiles, grain and keys, open points (client profiler plug-in if integrated) | agent runs `nb_p1_baseline` | `@p1-baseline` |
| CP1 | Decision per open point | worker, in the chat | `@x-approve` |
| P2.1 | Documents: inventory, triage, redacted extracts | agent runs `nb_p2_documents` | `@p2-1-triage` |
| P2.2 | Documents compared with the baseline | agent | `@p2-2-compare` |
| P2.2b | What the application does: app brief, dependencies, process and conceptual models (Glean conceptual first) | agent | `@p2-2b-understand` |
| P2.3, P2.4 | Scope and privacy proposal, column meanings; questions never block | agent | `@p2-3-scope` |
| CP2 | Brief, models and scope | worker, in the chat | `@x-approve` |
| P3 | Central model: logical silver model | agent | `@p3-logical` |
| CP3 | Central model — required before P4 | worker, in the chat | `@x-approve` |
| P4 | STTM: draft from the approved model, validate, review, export with the client template | agent | `@p4-sttm` |
| CP4 → H1 | STTM approved; handoff package for the build | worker, in the chat | `@x-approve` |
| P5 | PySpark notebooks from the STTM, shared masters, QA on dev silver, code review | agent | `@p5-1-codegen`, `@p5-4-masters`, `@p5-2-qa`, `@p5-3-code-review` |
| CP5, CP6 | Automatic checks (no person) | framework | `python -m b2s cp-auto` |
| P6 → H2 | Readiness package for deployment | agent | `@p6-1-release` |

The worker starts with **`@b2s-run`** in the Genie chat. The agent reads the status, runs the next step, asks for
checkpoints, and reruns what became stale after new input.

## What makes it reliable
- **Files only, safe:** every state file is written once with its version in the name (`logical.v004.yaml`) and a sidecar that names the input versions it was made from. Events record who did what, and how (`run_by: genie | person`).
- **Stale detection:** new input, a new version or a framework change marks dependent outputs stale; the status shows why and what to rerun.
- **Checkpoints in the chat:** `I, Jane Doe, approve CP3 logical.v004.` The template is pre-filled; the tool refuses a changed file, a wrong version, a missing name. One worker per application, no maker-checker: the handoff says so.
- **Mermaid is the record:** every model has YAML (truth), Mermaid, and an HTML viewer that is checked to match the Mermaid (no overlapping boxes, readable contrast).
- **Privacy:** values of personal-data, secret, log and free-text columns are removed before anything is written.
- **Glean conceptual first:** what the application does and depends on, before any column; raw replies saved first.
- **Plug-ins:** client notebooks and templates come in through slots with contract tests (`@fw-integrate`).

## Quick start (local, no Databricks)
```bash
pip install -r requirements-ci.txt
python -m pytest                                    # the whole suite
python -m b2s.demo.walkthrough /tmp/b2s-demo        # fake application, bronze to handoff
```
Open `/tmp/b2s-demo/proj/apps/S90_yardops/work/P3/models/logical.v001.html` to see the model viewer.

## On Databricks
1. Add this repository (a release) as a Git folder in the workspace. Workers do not commit to it.
2. Run `notebooks/nb_doctor` once: workspace checks K-01 … K-08 with PASS / FAIL, saved as capabilities the code follows.
3. `python -m b2s --project <folder> install-skills <your Genie skill folder>`; Genie reads `AGENTS.md`.
4. In the Genie chat: `@p0-setup` (first use integrates your profiler notebook and STTM templates), then `@b2s-run`.
   A new chat starts from `python -m b2s --project <folder> status <app> --brief`.

Status: built and tested locally (fake application); not yet run on a Databricks workspace. See the verification
table in [`docs/V1_4_DESIGN.md`](docs/V1_4_DESIGN.md) §14.

## Repository
| Path | What |
|---|---|
| `AGENTS.md`, `rules/` | rules for Genie Code |
| `skills/` | one skill per step, `@b2s-run`, `@x-approve`, `@x-research`, `@x-input`, `@x-model-view`, `@fw-integrate` |
| `notebooks/` | `00_start_here`, `nb_doctor`, `nb_p1_baseline`, `nb_p2_documents`, `nb_p5_qa` (run by the agent) |
| `b2s/` | the framework package (`python -m b2s ...`) |
| `lib/`, `standards/` | PySpark runtime library and client standards used by the generated silver notebooks |
| `plugins/` | core plug-ins (defaults for each slot) |
| `registry_template/` | ontology and registries copied into a new project |
| `tests/` | unit, flow and end-to-end tests |
| `docs/` | design (with verification status), migration from V1.3, review notes |

## License
Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE). Not affiliated with Databricks, Inc.
