---
name: p5-1-codegen
description: Step P5.1. Generate one PySpark notebook per STTM table from the CP4-approved STTM, complete the TODO(genie) cells, and run the notebooks on the dev silver schema. Use after CP4, and again when a new STTM version is approved.
---

# P5.1 Code generation

## Steps
1. `python -m b2s build <app> --via genie` — refuses unless the latest STTM version is approved at CP4. It writes `work/P5/build/notebooks/nb_slv_<app>_<table>.vNNN.py`, the master build notebooks (P5.4) and `build/index` (with the run order).
   Safe to re-run: GENERATED cells are refreshed, your TODO cells are kept, a TODO cell whose STTM spec changed gets a `# REVIEW(STTM changed)` block.
2. Complete every `# TODO(genie)` cell: filters and dedup, `bronze_count` (row count after filter + dedup), derived and open columns. Follow `standards/coding.md`; use `lib.keys.normalise` for keys. Never change a GENERATED cell — change the STTM instead (new version, CP4 again).
3. Remove each REVIEW block after you checked the code below it.
4. Save each notebook as a new version: `python -m b2s build-save <app> <notebook file> --reason "TODO cells completed" --via genie` (refused if a GENERATED cell was edited).
5. Run the notebooks yourself in the workspace, in the run order of `build/index`: staging for masters → master builds (`@p5-4-masters`) → tables → tables with foreign keys. They write to the DEV silver schema of the project settings only.

Then `@p5-2-qa`.
