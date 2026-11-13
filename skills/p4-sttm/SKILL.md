---
name: p4-sttm
description: Step P4 (P4.1 STTM, P4.2 validate, P4.4 export). Build the source-to-target mapping (STTM) from the approved logical model, export it with the client template plug-in, and prepare the CP4 handoff approval. Use after CP3 is approved, and after any change that makes the STTM stale.
---

# P4 Mapping: STTM

## Steps
1. `python -m b2s draft-sttm <app>` — refuses unless the logical model version is approved (CP3). It writes `sttm/sttm.vNNN.json`, the mapping model, the Excel export (`sttm.vNNN.xlsx`, through the export plug-in; P4.1 is the slot for the team STTM generator) and questions for anything it cannot map (no duplicates on reruns).
2. Complete the mapping: business-logic columns name their rule, FKs have `fk.lookup_on`, personal-data columns carry the privacy handling from CP2. Save as a new version with a reason.
3. `python -m b2s check <app>` must print `CHECKS OK`.
4. Show the mapping view (`@x-model-view`, model `mapping`).
5. P4.3 review in a new chat stays as in V1.3. Then ask for **CP4** (`@x-approve`). The template lists each open question and assumption, pre-filled; the worker decides accept or must answer. The handoff package is built when no `must answer` question is open.

The STTM is the contract with team 2. Do not "fix" a mapping in code later.
