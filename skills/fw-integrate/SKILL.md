---
name: fw-integrate
description: Integrate a new deterministic asset (a notebook such as a bronze profiler, a template such as the client STTM Excel or JSON, a document extractor) into the framework through a plug-in slot. Worker mode installs it as a project plug-in and makes a contribution package for the maintainers; maintainer mode moves it into core.
---

# @fw-integrate — integrate a new notebook or format

Slots and contracts: `python -m b2s plugin list`, `b2s/plugins.py` (SLOTS), `docs/V1_4_DESIGN.md` §15.

Used on **first use** of the framework (`@p0-setup` step 3) for the client's own assets, and later whenever a new
deterministic notebook or format arrives.

## Worker mode
1. Read the new asset. Find the slot it fits (profiler, sttm_export_excel, sttm_export_json, sttm_import_excel, doc_extractor, key_rules). None fits → write a proposal for a new slot for the maintainers and stop.
2. Make a folder `plugin-src/<name>/` with `plugin.yaml` and an adapter. Do not change the asset itself.
   - **Python asset** (a function or template writer): `kind: python`, `entry: adapter.py:<function>` implementing the slot contract.
   - **Notebook asset** (e.g. the client's bronze profiler): `kind: notebook`, copy the notebook unchanged into the folder (`notebook: <file>`), list its widgets under `parameters` (placeholders `{app}`, `{project_root}`, `{run_dir}`, `{schema}`), and write `adapter.py:convert(run_dir)` that turns the files the notebook writes into the slot contract. Add `sample_output/` with the real output of one run on non-personal test data — the contract test runs `convert` on it.
   - Example `plugin.yaml` (notebook): `name: client_profiler`, `slot: profiler`, `kind: notebook`, `version: 2.1.0`, `notebook: client_profiler.py`, `parameters: {schema: '{schema}', output_folder: '{run_dir}'}`, `entry: adapter.py:convert`, `description: ...`.
3. `python -m b2s plugin install plugin-src/<name>` — runs the contract test (e.g. an export must keep every table, column and open item).
4. Ask the worker to approve it in the chat: `I, <your name>, approve PLUGIN <name>.v<version>.` then `python -m b2s plugin activate <name> --statement-file -` with the reply on stdin, exactly as typed.
5. From now on the plug-in overrides the core one; every run records its version and approval pages show the override. A notebook plug-in is run by the agent in the step that uses it (`@p1-baseline` for the profiler: `plugins.run_plan` gives the notebook and widgets, `plugins.collect` converts its output).
6. `python -m b2s plugin package <name> --note CHANGE_NOTE.md` — the zip in `contrib/` goes to the maintainers.

## Maintainer mode (core repository)
1. Unpack the contribution; run its contract test and the full suite (`python -m pytest`).
2. Move it to `plugins/` (origin core) or merge it into the core slot; update `CHANGELOG.md` and `FRAMEWORK_VERSION`.
3. A new slot needs a contract in `SLOTS`, a contract test, and a design note.
