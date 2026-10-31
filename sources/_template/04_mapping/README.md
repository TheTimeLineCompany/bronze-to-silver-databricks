# 04_mapping - P4 Mapping (checkpoints CP4_sttm, CP4b_business_logic)

Purpose: the source-to-target mapping (STTM), traced to business objects and evidence.

| Path | Written by | Read by |
|---|---|---|
| `sttm.yaml` | p4-1-sttm-author (single source of truth) | validator, codegen |
| `exports/sttm.xlsx`, `exports/er.mmd` | `tools/p4_4_export_sttm.py` (never edit) | people, phase 2 |
| `reviews/sttm_review.md` | p4-3 (new chat) | checkpoint check |
| `reviews/business_logic_signoff.md` | client SME | checkpoint check |
| `checkpoint/CP4_sttm.*`, `checkpoint/CP4b_business_logic.*` | `tools/x_checkpoint_pack.py` | reviewer, SME, phase 2 |
| `feedback/CP4_sttm/`, `feedback/CP4b_business_logic/` | reviewers, agents | p4-1 at rerun |

Handover H1 to phase 2 after CP4 and CP4b: this folder + `02_evidence/evidence_register.csv`.
