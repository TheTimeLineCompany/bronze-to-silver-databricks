---
name: p4-3-sttm-review
description: Step P4.3. Independent review of one STTM in a NEW chat with an explicit checklist - grain, keys, joins, FKs, ontology fit, evidence and confidence, business logic, history, and questions - and write sources/<id>/04_mapping/reviews/sttm_review.md with Result PASS or FAIL. Use after p4-2-sttm-validate passes, never in the chat that wrote the STTM.
---

# P4.3 STTM review (phase P4, checkpoint CP4_sttm)

## Important
Run in a **new chat**. The authoring chat carries its own reasoning and misses its own mistakes.

## Inputs
- `04_mapping/sttm.yaml`, validator output (must have no errors)
- `01_intake/source_brief.md`, `02_evidence/evidence_register.csv`, `02_evidence/discovery/summary.md` + `links.csv`, `02_evidence/profiling/`
- `registry/ontology/*.yaml`, `registry/entities.yaml`, `registry/key_normalisation.yaml`
You may open an inbox file ONLY to spot-check a cited evidence location.

## Checklist (write evidence for each FAIL)
**Ontology fit**
- [ ] Each table's business object and data class are right for what the rows ARE (not what the source calls them).
- [ ] Each FK follows a business relationship and its cardinality.
**Grain and keys**
- [ ] The grain sentence matches the bronze key in `discovery/tables.csv` (or a stated superset of it).
- [ ] The business key is unique after filter and dedup; key rules come from the registry.
- [ ] Masters use the registry table, business key, and history.
**Joins**
- [ ] Join cardinality matches profiling; no join multiplies rows beyond the grain.
**Columns and evidence**
- [ ] Spot-check at least 5 evidence ids: open the location and confirm the claim.
- [ ] No key or business-logic column rests on low/unknown evidence only.
- [ ] Types fit the profiled data (dates, time zones, decimals).
- [ ] Transforms are exact. No vague text such as "clean up".
**Business logic and history**
- [ ] Each business_logic column names a BR id, and the formula matches the rule text.
- [ ] Load pattern fits the data class and how changes arrive.
**Questions and feedback**
- [ ] Every low-confidence column has a question; no blocking question is hidden.
- [ ] Each applied feedback item for CP4 is really reflected in the STTM.

## Output
Copy `templates/review.md` to `04_mapping/reviews/sttm_review.md`. Exactly one line `Result: PASS` or `Result: FAIL`.
FAIL: a reviewer may also turn findings into feedback items: `python tools/x_feedback.py new <id> CP4_sttm --comment "..."`.

## Rules
Report; do not fix the STTM in the review chat.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p4-3-sttm-review --comment "..." --blocks CP4_sttm`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
