---
name: p2-2-compare
description: Step P2.2. Compare what the documents say with the bronze baseline - each document fact confirms the baseline, contradicts it, or adds something new. Use after P2.1 (documents) and P1 (baseline) exist, and again when either changes.
---

# P2.2 Compare documents with the baseline

Bronze wins for structure (keys, nulls, formats). Documents win for meaning. Record both; do not choose silently.

## Inputs
`baseline/summary.vNNN.json`, document evidence from `@p2-1-triage`, extracts of core files (already redacted).

## Steps
1. For each document claim about tables, keys, codes or relationships, check the baseline:
   - **confirms** → update the evidence status to `confirmed_by_bronze`.
   - **contradicts** → mark it `contradicted`, add the bronze fact as evidence, raise a `Q-` for the meaning.
   - **adds** (the baseline cannot say, e.g. a business rule, a workflow) → keep it as evidence with its confidence.
2. Tables the documents name that are not in bronze, and bronze tables no document names: list both.
3. Write `documents/comparison.yaml`:
   ```yaml
   facts:
     - {evidence: E-0012, result: confirms, about: yard.mv_leg}
     - {evidence: E-0015, result: contradicts, about: yard.mv_plan.plan_status, question: Q-0007}
     - {evidence: E-0018, result: adds, about: "workflow: plan approval"}
   documents_only: [yard.berth_plan]
   bronze_only: [yard.rate_card]
   ```
4. Save: `python -m b2s save <app> documents/comparison <file> --reason "..." --via genie`.
5. No documents for this application? Save a comparison with empty lists and a note; the gaps become assumptions in P2.2b.

Then `@p2-2b-understand`.
