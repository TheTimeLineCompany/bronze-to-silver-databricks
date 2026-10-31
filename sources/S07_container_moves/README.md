# Source S07_container_moves

One folder per source system. Folder number = phase number. P3 (central model) is global: see `registry/`.

| Folder | Phase | Checkpoint | Holds |
|---|---|---|---|
| `00_inbox/` | input | - | The client dump, as delivered. Never edit, sort, or delete here. |
| `01_intake/` | P1 Intake and focus | CP1_source_brief | Manifest, triage, source brief |
| `02_evidence/` | P2 Discovery and evidence | CP2_evidence | Evidence register, client profiling, bronze discovery |
| `04_mapping/` | P4 Mapping | CP4_sttm, CP4b_business_logic | STTM (truth), exports, reviews |
| `05_build/` | P5 Build | CP5_code_qa | Notebooks, job, QA results, code review |
| `06_handoff/` | P6 Handoff | CP6_handoff | Readiness report |
| `run_log.jsonl` | all | - | One line per agent run |

Each phase folder has the same three sub-folders:
- `checkpoint/` - the checkpoint pack: `<CP>.html` (open first), `<CP>.xlsx`, `<CP>.json`, `<CP>.md`. Made by `tools/x_checkpoint_pack.py`.
- `feedback/<CP>/` - feedback items `FB-xxxx.yaml` (human) and upstream issues (agent), plus `attachments/`.
- `reviews/` - review files with `Result: PASS` or `Result: FAIL` (P4 and P5 only).
