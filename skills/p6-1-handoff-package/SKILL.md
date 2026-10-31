---
name: p6-1-handoff-package
description: Step P6.1. Assemble the deployment package for one source - exports, notebooks, job, QA evidence, reviews - and write sources/<id>/06_handoff/readiness.md with run order, known limitations, and deployment notes. Use after CP5 is approved, before checkpoint CP6 and handover H2 to the deployment team.
---

# P6.1 Handoff package (phase P6, checkpoint CP6_handoff, handover H2)

## Preconditions
- `python tools/x_validate_gate.py --next <id>` shows the next checkpoint is `CP6_handoff`.
- No open blocking question for this source in `registry/open_questions.yaml`.

## Steps
1. Run `python tools/p4_4_export_sttm.py sources/<id>/04_mapping/sttm.yaml` again so exports match the final STTM.
2. Fill `06_handoff/readiness.md` from `templates/readiness_report.md`:
   - deliverables with paths, target tables (grain, data class, load pattern, rows in dev, dependencies);
   - run order (masters first), schedule, required grants, parameters per environment, rollback;
   - non-blocking questions and known limitations;
   - feedback history: `python tools/x_feedback.py list <id>` (all items verified or rejected).
3. Run `python tools/x_validate_gate.py <id>`. Fix every error.
4. Open the PR that sets `CP6_handoff` to `in_review`. The deployment lead approves.

## Handover H2 package
`05_build/` notebooks + job, `05_build/qa_results/summary.json`, `06_handoff/readiness.md`, `04_mapping/exports/`.

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py <id> CP6_handoff`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p6-1-handoff-package --comment "..." --blocks CP6_handoff`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
