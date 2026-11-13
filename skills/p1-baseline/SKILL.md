---
name: p1-baseline
description: Step P1. Run the bronze baseline for one application (S0 inventory, S1 column profile, S2 grain and keys, S5 report) by running the nb_p1_baseline notebook - with the client's profiler notebook first when it is integrated - explain the open points, do the CP1 Glean check, and ask for CP1 in the chat. Use for a new application, when bronze changed, or when the status says P1 is stale.
---

# P1 Bronze baseline

## 1. Run
1. Client profiler integrated? (`python -m b2s plugin list` shows `profiler ... (project)`)
   - Yes: `python -c "from b2s import plugins; from b2s.project import open_project as o; print(plugins.run_plan(o('<p>'), '<app>', 'profiler', {'schema': '<schema>'}))"` gives the notebook, its widgets and `run_dir`. Run that notebook with those widgets. Then pass `run_dir/plan.json` to the baseline notebook as `profiler_run`.
   - No: leave `profiler_run` empty (core profiler).
2. Run `notebooks/nb_p1_baseline` with `project_root`, `app`, `run_by = genie`, `profiler_run`. Use `fresh_run = yes` only after a framework fix, with a reason.
3. `partial: True` → run it again until it is complete (it resumes; unchanged tables are skipped).

## 2. Read and explain
Read `baseline/summary.vNNN.json` only (never table data). Tell the worker in a few lines: tables, keys found, and the open points:
- **no key** / **no key within limits** (the limits are in the result) / **near key** (duplicates count)
- **copy of** another table, **empty** table, tables whose columns a rule removed from the key search (`removed_by_rule`)

## 3. CP1 Glean check
For each open point that would become a client question, ask Glean first (`@x-research`, type `conceptual`, one topic per open point; never put values into the question). Integrate the answers as evidence; an open point Glean settles gets a note.

## 4. CP1
`@x-approve` with `CP1`. The template lists each open point, pre-filled `accept`; the worker changes any line to `change`, `question` or `defer`.
CP1 does not block P2: continue with `@p2-1-triage` while the worker reviews.
