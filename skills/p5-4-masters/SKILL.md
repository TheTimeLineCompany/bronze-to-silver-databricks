---
name: p5-4-masters
description: Step P5.4. Build the shared masters (one notebook per entity in _project/entities.yaml) from the staging tables of every application that maps the entity, with the survivorship rules. Use after P5.1, before running tables that have foreign keys to a master.
---

# P5.4 Master build (shared masters)

No application notebook writes a shared master: each writes its own staging table (`slv_stg_<master>_<app code>`).
The master build reads all staging tables, applies survivorship from `_project/key_normalisation.yaml`, loads the
master (scd2 or merge) and seeds the unknown member.

## Steps
1. `python -m b2s build <app>` writes `masters/<table>/nb_build_<table>.vNNN.py` (project level) and `build/masters`.
2. Read the problems in `build/masters`. An entity fed by two or more applications needs survivorship rules: propose them as a change request and ask the project owner; never invent priorities.
3. Run each master build notebook yourself after the staging notebooks that feed it, before the tables whose foreign keys point to the master.

Then `@p5-2-qa`.
