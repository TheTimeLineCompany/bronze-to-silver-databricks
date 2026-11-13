# Checkpoints, approved in the chat

Linked from `AGENTS.md` rule 4. Design: `docs/V1_4_DESIGN.md` §12.

The V1.3 checkpoints stay. What changes: the worker approves in the Genie chat, with their name and the file
versions, instead of editing files. The worker approves their own work; there is no maker-checker. Team 2 is the
first second pair of eyes, so the handoff states that it is self-approved.

## Checkpoints (team 1, up to the STTM)
| Checkpoint | Approves (exact versions) | Blocks |
|---|---|---|
| CP1 bronze baseline | baseline summary + a decision per open point (accept, change, question, defer) | — |
| CP2 documents, application understanding, scope | app brief, dependencies, process and conceptual models, scope (nothing left in `review`; every personal-data column has keep_tagged, mask or hash) | CP3 approval (chain) |
| CP3 central model | logical silver model | **P4 STTM** |
| CP4 STTM | STTM + a decision per open question and assumption (accept, must answer) | **the handoff H1** |

CP3b (key rules) and CP4b (business logic) stay as in V1.3 for now.

## How
1. `python -m b2s approve request <app> <checkpoint> --via genie`. If it refuses, tell the worker the reasons in plain words and fix them first (rerun a step, ask for a scope decision, ask for an upstream approval).
2. Show the chat text exactly. It ends with the statement template, pre-filled except the name:
   `I, <your name>, approve CP3 logical.v004.`
   At CP1 and CP4 the decisions follow, one per line, pre-filled with the worker's previous decisions.
3. Wait for the worker's reply. Pass it **verbatim**:
   `python -m b2s approve record <app> <AR-id> --statement-file - --via genie` with the reply on stdin, exactly as typed
   (a here-document; never inside shell quotes — quotes and line breaks in a statement must arrive unchanged)
4. Report the result. If it refuses (a file changed, a version differs, a name or decision is missing), say why and ask again — a new request shows the new version.

## Never
- Write, complete, correct or rephrase a statement. Not even "just approve it" from the worker: show the template they need to type.
- Treat "OK", "yes", "looks good", a thumbs-up or silence as an approval.
- Edit a request file or an approval item.

A reply with changes instead of an approval is an input: create an `IN-` item and route it (`@x-input`).
