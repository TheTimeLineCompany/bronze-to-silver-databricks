---
name: x-feedback-rerun
description: Cross-phase. Record human feedback at any checkpoint (CP1 to CP6, CP3, CP3b) as a feedback item - a comment, folder or file paths to include or ignore, a code snippet, a data slice (table plus filter), attachments, or an answer - then plan and run the rerun of the affected steps, reset later checkpoints, and close the loop. Use whenever a person reviews an output and wants something changed.
---

# X Feedback and rerun (any phase, any checkpoint)

## The loop
```
person reviews output at CPn  ->  FB-xxxx.yaml (status open)
agent: plan -> reset -> rerun steps -> set applied (summary, changed files)
person: checks -> verified (or rejected with reason, or new feedback)
checkpoint can be approved only when no item is open / in_progress / applied
```

## 1. Capture (person, or agent on behalf of a person)
Quick: `python tools/x_feedback.py new <id> <CP> --comment "..." [--include 00_inbox/X/] [--ignore 00_inbox/Old/] [--code "..."] [--data-table bronze.s.t --data-filter "..."] [--attach path] [--target-artifact 04_mapping/sttm.yaml --target-location tables[0].columns.eta_ts] [--rerun-from <step>]`
Full: copy `templates/feedback.yaml` to `sources/<id>/<phase folder>/feedback/<CP>/FB-xxxx.yaml` (global: `registry/feedback/<CP>/`). Mix any kinds in one item.

| Kind | Example | Used by |
|---|---|---|
| comment | "ETA text is local port time" | any step |
| include_paths | `00_inbox/03_Workshops/` | P1.2 triage, P2.3 |
| ignore_paths | `00_inbox/Archive/` | P1.2 triage |
| code | a PySpark or SQL snippet for a cell or a transform | P4.1, P5.1 |
| data | `{table, filter, columns, note}` | P2.2 profiling, P5.2 QA |
| attachments | a new file placed in `<phase folder>/feedback/<CP>/attachments/` | P1.1 (inventory it), P2.3 |
| answer | `{question: Q-0001, text: ...}` | P2.3 (client_answer evidence) |

## 2. Plan and reset (agent)
1. `python tools/x_feedback.py plan FB-xxxx --source <id>` -> `rerun_now`, `then_recheck`, `reset_checkpoints`.
2. `python tools/x_feedback.py set FB-xxxx in_progress --source <id>`.
3. `python tools/x_feedback.py reset FB-xxxx --source <id>` -> later checkpoints go back to `pending` (by PR).

## 3. Rerun (agent)
- Run each step in `rerun_now` with its skill (`@p2-3-evidence-reconcile`, ...). Use ONLY the feedback content plus the step's normal inputs. Do not re-read the whole inbox.
- For `then_recheck` steps: run their validators; rerun the step only if its inputs changed.
- Log each run: `python tools/x_feedback.py log <id> <step> --feedback FB-xxxx --note "..." --outputs <files>`.

## 4. Close
- Agent: `python tools/x_feedback.py set FB-xxxx applied --source <id> --summary "<what changed>" --changed <files>`.
- Person: checks the change -> `set FB-xxxx verified --by <name>`, or `rejected` with a reason, or new feedback.

## 5. Upstream issues (agent -> earlier phase)
A later step that finds a problem owned by an earlier phase raises it; it never works around it.
```
python tools/x_feedback.py raise <id> <earlier CP> --step <your skill> --comment "..." --blocks <your CP> [--related FB-xxxx]
```
- Status `proposed`. A person triages: `x_feedback.py accept FB-xxxx --source <id>` (-> open, then sections 2-4) or `set FB-xxxx rejected --summary "<reason>"`.
- `--blocks`: your own checkpoint cannot be approved until the item is verified or rejected.
- `--related`: the same problem came back. The third attempt fails the checkpoint check: a person must decide (loop guard).
- Global problems (a new business object, a key rule): use source `global` and checkpoint `CP3_central_model` or `CP3b_key_rules`.

## 6. The board
`python tools/x_checkpoint_pack.py board` -> `registry/board/feedback_board.(html|xlsx|md|json)`: all items, who raised them, what they block.

## Ids
New items get `FB-<source code>-<4 random characters>` (for example `FB-S07-k2q9`, global `FB-GLB-7mxa`), so parallel
branches never pick the same id. The checkpoint check fails if two files still share an id after a merge.

## Rules
- Never set `verified` yourself. Only the person who reviews does.
- Feedback cannot change the ontology or registry directly. If it needs that, raise a change request (`@p3-1-entity-model`).
- If feedback conflicts with bronze evidence, report the conflict; do not apply it silently.
