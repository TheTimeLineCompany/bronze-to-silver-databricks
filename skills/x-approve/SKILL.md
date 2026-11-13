---
name: x-approve
description: Ask the worker to approve a checkpoint (CP1, CP2, CP3, CP4) in the chat and record their statement exactly as typed. Use when a checkpoint's files are new or changed, when the worker says they want to approve, or before P4 (needs CP3) and the handoff (needs CP4).
---

# @x-approve — checkpoints approved in the chat

Read `rules/approvals.md` first.

## Steps
1. `python -m b2s status <app>` — see which checkpoints are `not approved` or `re-approval needed`.
2. `python -m b2s approve request <app> <checkpoint> --via genie`
   - Refused? Explain the reasons in plain words and fix them first. Typical: a step is stale (rerun it), a scope item is still `review` (ask the worker and save the decision with `python -m b2s scope ...`), an upstream checkpoint is missing (ask for it first).
3. Show the chat text exactly as the tool gives it. It ends with the template, pre-filled except the name, e.g.
   ```
   I, <your name>, approve CP3 logical.v004.
   ```
   Point to the page `review/approvals/AR-nnnn.html` (it embeds the model viewer).
4. Wait for the worker's reply. Then:
   `python -m b2s approve record <app> <AR-id> --statement-file - --via genie` with the reply on stdin, exactly as typed
   (a here-document; never inside shell quotes — quotes and line breaks in a statement must arrive unchanged)
5. Report: recorded (and at CP4: the decisions, and the handoff folder or the questions it waits for), or the reason it was refused. If a file changed, make a new request.

## Never
- Type, complete, correct or rephrase the statement for the worker.
- Accept "OK", "yes", "looks good" or silence as an approval.
- Record an approval for a request you did not show in this chat.
