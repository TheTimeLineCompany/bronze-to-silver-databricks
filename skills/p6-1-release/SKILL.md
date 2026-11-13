---
name: p6-1-release
description: Step P6.1 and the automatic checkpoints CP5 and CP6. Run the CP5 checks, write the readiness package, run the CP6 checks, and hand the H2 package to the deployment team. Use after P5.3 gave "Verdict: pass".
---

# P6.1 Readiness and handoff H2

CP5 and CP6 are automatic: no person approves them; the framework checks do (V1.3).

## Steps
1. `python -m b2s cp-auto <app> CP5` — checks: STTM approved at CP4, notebooks current, no REVIEW block, no unfinished TODO cell, no hand-edited GENERATED cell, dev schema only, master problems, QA coverage and all checks passing, code review `Verdict: pass`. Not passed → fix each problem (the list says which step), then run it again.
2. `python -m b2s release <app>` — writes `release/readiness.vNNN.md`: inputs, run order, accepted assumptions from CP4, notebooks. Not complete → fix the problems it lists (for example a question marked "must answer" at CP4 that is still open).
3. `python -m b2s cp-auto <app> CP6` — passes when the readiness is complete; it builds `handoff/H2-nnn/` (notebooks, master builds, QA results, readiness, STTM, approvals, manifest).
4. Tell the worker the H2 folder. Promotion from dev to test and prod is the deployment team's job.
