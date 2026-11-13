---
name: p0-setup
description: Step P0. Set up a project folder, integrate the client's own notebooks and templates on first use (bronze profiler, STTM Excel and JSON templates, other helpers) with @fw-integrate, and register applications. Use when there is no project yet, on first use of the framework in a workspace, or when a new application must be added.
---

# P0 Setup (once per project) and first-use integration

## 1. Workspace checks (first time in a workspace)
Run `notebooks/nb_doctor` (widgets: `project_root`, `run_by = genie`; optionally one view and its base table for K-04).
It prints PASS / FAIL / MANUAL for K-01 … K-08 and writes `capabilities` into `project.yaml` (the code follows them,
e.g. the lock method). A FAIL on K-01 or SHARED stops here: tell the worker what to fix. Report the MANUAL items.
Then run `notebooks/00_start_here` with `action = setup-check`; it must print `SETUP OK`.

## 2. Project
No `project.yaml` yet → run `00_start_here` with `action = new-project` (`text` = project name). It pins the framework version and copies the ontology into `_project/`.

## 2b. Skills where Genie loads them
`python -m b2s --project <p> install-skills <your skill folder>` (for example `/Workspace/Users/<me>/.assistant/skills`).
`status --brief` warns when the installed skills do not match the framework version.

## 3. First use: integrate the client's assets (once per project)
`python -m b2s --project <p> plugin list` shows each slot and whether it runs the core default.
Ask the worker, in ONE message, for the workspace paths of the assets they already use:
- the bronze profiler notebook → slot `profiler` (kind `notebook`)
- the STTM Excel template → slot `sttm_export_excel`
- the STTM JSON template → slot `sttm_export_json` (and `sttm_import_excel` if they edit STTMs in Excel)
- any other deterministic notebook or format they rely on (document extractor, key rules)

For each one: `@fw-integrate` (worker mode). Each needs the worker's approval in the chat:
`I, <your name>, approve PLUGIN <name>.v<version>.`
An asset that fits no slot → `@fw-integrate` writes a proposal for the maintainers; continue with the core default.

## 4. Register an application
Ask for: application id (`S01_name`), name, bronze schemas, lookup schemas. Then run `00_start_here` with `action = register-app` (`app`, `text` = schemas comma-separated, `text2` = lookup schemas).
Ask the worker to put the application's documents into `apps/<app>/inbox/` (as they are; sub-folders are kept).

Then `@b2s-run`.
