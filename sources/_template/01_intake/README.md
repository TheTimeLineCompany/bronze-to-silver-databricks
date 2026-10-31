# 01_intake - P1 Intake and focus (checkpoint CP1_source_brief)

Purpose: make the dump small and known, then write one short brief.

| File | Written by | Read by |
|---|---|---|
| `manifest.csv` | `tools/p1_1_inventory.py` | code, people |
| `manifest.md` | `tools/p1_1_inventory.py` | agent (the only inventory file it reads) |
| `triage.yaml` | p1-2-triage (agent), confirmed by a person | p1-3, p2-1, checks |
| `source_brief.md` | p1-3-source-brief | every later step |
| `checkpoint/CP1_source_brief.*` | `tools/x_checkpoint_pack.py <id> CP1_source_brief` | reviewer, next phase |
| `feedback/CP1_source_brief/` | reviewers, agents (upstream issues) | p1-2, p1-3 at rerun |

Next: P2 reads `source_brief.md` and the evidence register, never `00_inbox`.
