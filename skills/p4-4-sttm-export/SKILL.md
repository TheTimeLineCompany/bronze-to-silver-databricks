---
name: p4-4-sttm-export
description: Step P4.4. Generate the human handoff files from an STTM - Excel workbook (summary, keys, one sheet per table with business object, data class, business rule, and evidence) and a Mermaid ER diagram. Use after the STTM review passes, and every time the STTM changes. Never edit the exports by hand.
---

# P4.4 STTM export (phase P4, checkpoint CP4_sttm; package for handover H1)

## Steps
1. Run `python tools/p4_4_export_sttm.py sources/<id>/04_mapping/sttm.yaml`.
2. Check `04_mapping/exports/sttm.xlsx` and `04_mapping/exports/er.mmd` exist.
3. Commit the exports in the same PR as the STTM.
4. CP4b: when the STTM has `business_logic` columns, send the Excel (sheet per table, column `business_rule`) to the client SME. The SME's result goes to `04_mapping/reviews/business_logic_signoff.md` (template: `../p4-3-sttm-review/templates/review.md`) with `Result: PASS`, or comes back as feedback in `04_mapping/feedback/CP4b_business_logic/`.

## Handover H1 (phase 1 -> phase 2)
After CP4 and CP4b are approved, phase 2 receives: the approved `sttm.yaml`, `exports/`, `evidence_register.csv`, `04_mapping/reviews/`, and the CP4 checkpoint pack.

## Rules
Exports are generated. Change the STTM, then export again.

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py <id> CP4_sttm` and, when business logic exists, `python tools/x_checkpoint_pack.py <id> CP4b_business_logic`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p4-4-sttm-export --comment "..." --blocks CP4_sttm`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
