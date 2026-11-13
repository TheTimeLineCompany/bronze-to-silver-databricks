---
name: p5-2-qa
description: Step P5.2. Make the QA plan and run the QA notebook on the dev silver schema; every check of the client's QA checklist must pass. Use after the generated notebooks and master builds ran, and after any rebuild.
---

# P5.2 QA

## Steps
1. `python -m b2s qa-plan <app> --via genie` — which checks of `standards/qa_checklist.md` apply to which dev table (staging tables for masters, the masters themselves).
2. Run the notebook `notebooks/nb_p5_qa` yourself (widgets: project folder, app, run_by = genie). It runs `lib/qa_checks.py` and saves `qa/results.vNNN.json`.
3. Read the result cell. A check that fails or cannot run (status `error`) is a problem to fix — in a TODO cell, in the STTM (new version, CP4 again), or in the data with the client. Never weaken a check.
4. Rerun the affected notebooks, then the QA notebook, until all checks pass.

Then `@p5-3-code-review` in a NEW chat.
