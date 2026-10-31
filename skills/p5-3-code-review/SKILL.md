---
name: p5-3-code-review
description: Step P5.3. Independent code review of one source's notebooks and Job in a NEW chat against the approved STTM, client coding and naming standards, and QA results, and write sources/<id>/05_build/reviews/code_review.md with Result PASS or FAIL. Use after p5-2-qa-runner passes, never in the chat that wrote the code.
---

# P5.3 Code review (phase P5, checkpoint CP5_code_qa)

## Important
New chat only. Report problems; do not fix them in the review chat.

## Inputs
`05_build/` notebooks and job, `05_build/qa_results/summary.json`, approved `04_mapping/sttm.yaml`, `standards/`, `lib/`.

## Checklist
- [ ] Every `# GENERATED` cell is unchanged (compare with a fresh `p5_1_gen_notebook.py` output).
- [ ] Each STTM column, join, filter, and dedup rule is in the code, exactly.
- [ ] Each business-logic column matches the CP4b sign-off formula and names its BR id.
- [ ] Lookups use the current master row and the registry key rule; orphan policy as in the STTM.
- [ ] Load pattern from `lib/load_patterns.py` matches the STTM; no hand-written merge logic.
- [ ] Naming and coding standards: widgets, no hard-coded catalog, no `collect()` on large data, comments on rules.
- [ ] QA summary: all pass, every checklist item present, no threshold changed.
- [ ] Job: one task per notebook, masters first, retries and timeout set.
- [ ] Applied CP5 feedback items are really in the code.

## Output
`05_build/reviews/code_review.md` from `../p4-3-sttm-review/templates/review.md`, exactly one line `Result: PASS` or `Result: FAIL`.
Findings can also become feedback items: `python tools/x_feedback.py new <id> CP5_code_qa --comment "..."`.

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py <id> CP5_code_qa`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p5-3-code-review --comment "..." --blocks CP5_code_qa`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
