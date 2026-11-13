---
name: x-input
description: Take a person's input at any time (typed instruction, feedback, an answer, an uploaded file), trace it against the ontology and the current models, route it to the steps that must use it, and rerun what becomes stale. Use whenever the worker gives new information or changes their mind.
---

# @x-input — input at any time

Work never waits for input, and input can always send work back.

## Steps
1. Record it: `python -m b2s item new <app> input --data '{"text": "...", "kind": "instruction|feedback|answer|file", "files": ["uploads/..."]}' --via genie`.
2. Trace it: which business objects, tables, columns, models, questions or assumptions does it touch? Names you do not know are new concepts — say so.
3. Ask at most 5 short clarify questions, only about what the trace could not settle.
4. Apply it as new versions with the reason `input IN-nnnn` (answer a question: `item update <app> Q-nnnn --data '{"status": "answered", "answer": "..."}'`; change a model; decide a scope; add a document to `uploads/`).
5. `python -m b2s status <app>` shows what became stale and the rerun plan. Rerun in that order; notebook steps (P1, P2.1) go to the worker.
6. If an approved version changed, tell the worker which approval must be given again.
7. Mark the input `applied` with a summary (`item update <app> IN-nnnn --data '{"status": "applied", "summary": "..."}'`).
