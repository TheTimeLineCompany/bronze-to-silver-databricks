---
name: p4-2-sttm-validate
description: Step P4.2. Run the deterministic STTM validator for one source and explain each error with the fix - structure, naming, keys, central model, ontology coherence (business object, data class, FK relationships, business rules), evidence ids, and confidence rules. Use after every change to sources/<id>/04_mapping/sttm.yaml.
---

# P4.2 STTM validate (phase P4, checkpoint CP4_sttm)

## Goal
A code check, not an opinion. The same script runs again as a PR check, so a prompt cannot skip it.

## Steps
1. Run `python tools/p4_2_validate_sttm.py sources/<id>/04_mapping/sttm.yaml`.
2. For each `ERROR`, find the line and say the fix in one sentence. Common errors:

| Error area | Typical cause | Fix |
|---|---|---|
| ontology: business_object | name is a source word, not the object | use the object name; add a synonym by P3.1 if needed |
| ontology: load pattern | not allowed for the data class | choose from `data.yaml` `allowed_load_patterns` |
| ontology: FK relationship | no relationship between the two objects | add it by change request (P3.1) or fix the FK |
| business_rule | business_logic without BR id | add `business_rule: BR-<DOM>-<nnn>` that exists in `business.yaml` |
| evidence | cited E-id not in the register | add the evidence (P2.3) or fix the id |
| confidence | key or business logic rests only on low/unknown evidence | verify in bronze (P2.2) or raise a question |
| status | approved while a blocking question is open | keep `draft` / `in_review` |

3. Fix errors in the STTM (or go back to the step that owns the cause). Run again until no errors.
4. Warnings: fix or explain each one in the review file.
5. Also run `python tools/x_ontology_check.py` when the STTM adds a new object or relationship.
6. Log the run with `tools/x_feedback.py log`.

## Done when
`PASS` with 0 errors. Then start `@p4-3-sttm-review` in a NEW chat.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p4-2-sttm-validate --comment "..." --blocks CP4_sttm`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
