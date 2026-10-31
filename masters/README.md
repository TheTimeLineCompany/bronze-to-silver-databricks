# masters - shared master builds (one folder per conformed entity)

Source notebooks never write a shared master (`slv_mst_*`) directly. Each source writes its own staging table
(`slv_stg_mst_<name>_<source code>`). The build here combines all staging tables of one entity with the
survivorship rules in `registry/key_normalisation.yaml` (approved at CP3b), loads the master (SCD2 or merge),
seeds the unknown member, and runs QA.

| Path | What | Made by |
|---|---|---|
| `<master table>/nb_build_<master table>.py` | build notebook | `tools/p5_4_gen_master_build.py <Entity>` (safe to re-run) |
| `<master table>/qa_results/summary.json` | QA of the master | the build notebook |

Run order in a job: source notebooks of the entity -> master build -> process tables that use the master.
CP5 of a source that feeds a master needs the master build QA to be complete and passing.
