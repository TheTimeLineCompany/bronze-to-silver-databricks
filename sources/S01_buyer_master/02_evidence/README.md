# 02_evidence - P2 Discovery and evidence (checkpoint CP2_evidence)

Purpose: prove each fact the mapping needs. Bronze data proves structure; documents prove meaning.

| Path | Written by | Read by |
|---|---|---|
| `evidence_register.csv` | p1-3, p2-3, `p2_2_discover.py evidence` | p4-1, reviews, validator |
| `profiling/doc_profiles.csv`, `doc_profiles_summary.md` | `tools/p2_1_extract_doc_profiles.py` (client workbooks) | p2-3 (by filter) |
| `profiling/*.json` | `tools/p2_2_profile_table.py` (targeted checks, feedback `data` items) | p2-3 |
| `discovery/summary.md` | `tools/p2_2_discover.py` | agent (read first) |
| `discovery/tables.csv`, `keys.csv`, `links.csv`, `columns.csv`, `domains.csv`, `derived.csv`, `graph.json`, `bronze_er.mmd` | `tools/p2_2_discover.py` | p2-3, p4-1, reviewers |
| `discovery/cards/T-xxx.md` + `.result.yaml` | code / one agent per card | `p2_2_discover.py merge` |
| `discovery/plan.yaml`, `job.json`, `tasks.jsonl`, `parts/` | orchestrator | code only |
| `checkpoint/CP2_evidence.*` | `tools/x_checkpoint_pack.py <id> CP2_evidence` | reviewer, P4 |
| `feedback/CP2_evidence/` | reviewers, agents | p2-2, p2-3 at rerun |
