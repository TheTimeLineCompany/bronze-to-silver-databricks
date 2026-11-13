---
name: b2s-run
description: Run the Bronze-to-Silver framework for one application - read the status, run the next step (including the notebooks), ask for checkpoints in the chat, rerun what is stale, and keep going until the worker stops or the handoff is done. Use when the worker says "run", "continue", "next", "where are we", or names an application.
---

# @b2s-run — the agent runs the framework

You orchestrate everything: notebooks, tools, skills and checkpoints. The worker gives input and approves
checkpoints in the chat; they do not run notebooks or edit files.

## Loop
0. New chat: `python -m b2s --project <project> status <app> --brief` gives the handover from the state; read it first.
1. `python -m b2s --project <project> status <app>` (no project yet → `@p0-setup`).
2. Take the first line under **Next** and do it:

   | Next says | You do |
   |---|---|
   | a skill (`@p1-baseline`, `@p2-1-triage`, … `@p4-sttm`, `@p5-1-codegen`, `@p5-4-masters`, `@p5-2-qa`, `@p5-3-code-review`, `@p6-1-release`) | run that skill — it runs its notebooks itself |
   | `blocked: CP1`…`CP4` | `@x-approve` for that checkpoint (the worker approves in the chat) |
   | `blocked: CP5` / `CP6` | `python -m b2s cp-auto <app> CP5` (automatic checks; report what failed) |
   | `stale` | rerun that step (same skill); say why in one line |
3. After each step: `python -m b2s check <app>`, then one short line to the worker: what ran, what changed, what is next.
4. Offer a checkpoint as soon as its files are ready (`not approved` or `re-approval needed` in the status). Never wait silently for an approval that blocks nothing; continue with other work.
5. Input from the worker at any time → `@x-input`, then back to step 1.

## Running a notebook
- Open the notebook in the framework folder, set its widgets (`project_root`, `app`, `run_by` = `genie`, and the step's own), and run all cells.
- Read the last line `B2S_STATUS {...}` (short JSON), then the `Result:` cells. If `partial` is true (time budget), run it again: it resumes.
- Never paste table data into the chat; read the summary files.
- Every notebook run is recorded in `events/` with `run_by: genie` and the workspace user.

## Stop and ask when
- A checkpoint must be approved (only the worker can type the statement).
- A refusal says the worker must decide (scope, privacy, a must-answer question).
- A notebook fails twice with the same error.
