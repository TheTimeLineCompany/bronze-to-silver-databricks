---
name: p2-3-scope
description: Step P2.3 (scope proposal, upgraded). Explain the columns of the in-scope tables, propose scope and privacy handling, and ask Glean only about columns the framework cannot explain. Use after the baseline and the conceptual model exist, or when either changed.
---

# P2.3 Scope proposal, column understanding and privacy

## Steps
1. `python -m b2s columns <app>` — writes `columns/columns.vNNN.yaml` (meaning, class, status known | inferred | unclear) and `scope/scope.vNNN.yaml` (proposal). Decisions already given by the worker are kept.
2. Improve meanings from evidence (documents, Glean conceptual answers). Save changes as a new version with a reason.
3. **Only now** ask Glean about `unclear` columns, grouped by table (`@x-research`, type `column`).
4. Scope decisions come from the worker, in the chat. For each table or column in `review`, and each personal-data column in scope, ask in one short list, then save each answer:
   `python -m b2s scope <app> <table or table.column> --scope in_scope|out_of_scope|derive_instead|technical --handling keep_tagged|mask|hash --reason "worker in chat: ..." --via genie`
5. P2.4: open questions stay open and do not block; record assumptions where you proceed.
6. When nothing is left in `review`, ask for **CP2** (`@x-approve`): app brief, models and scope together.

Application logs, audit columns, copies and secrets stay out of silver unless the worker gives a reason.
