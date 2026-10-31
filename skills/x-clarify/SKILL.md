---
name: x-clarify
description: Cross-phase. Quiz the person at the start of each checkpoint (kickoff) and after each new input (typed instruction, feedback, uploaded file). Think the input through against the evidence, discovery, ontology, and earlier instructions, ask at most 7 short questions in chat, and record the answers as instructions, evidence, feedback, or client questions. Use when the navigator shows "Clarify with you" or "Think through your input".
---

# X Clarify (kickoff and every new input)

People know things the documents do not say. Their input is often short or incomplete. Ask before you work, not after.

## When
| Point | Typed text | What you think through |
|---|---|---|
| Kickoff of a checkpoint | `@x-clarify kickoff for <id>` | the scope, weak or contradicted evidence, tables and columns in review, documents vs bronze gaps, open client questions |
| New input | `@x-clarify input <IN-xxx or FB-...> for <id>` | the input itself: is it clear, does it fit the evidence, ontology, and earlier instructions, what does it change |

## Steps
1. Run `python tools/x_clarify.py brief <id>` (kickoff) or `python tools/x_clarify.py brief <id> --input <ref>`.
   It writes `<phase folder>/clarify/QZ-<CP>-nnn.md` with facts and draft questions. A rerun returns the same open questionnaire.
2. Read the facts. Read also: active instructions (`sources/<id>/instructions.yaml`), the input's attached files, and only the
   evidence rows, discovery rows, and ontology entries that the facts name. Do not read the whole inbox.
3. Think it through with this checklist. Keep a question only if the answer changes the work:
   - **Clarity**: what exactly must change, where, and how will the person check it?
   - **Conflict**: does it disagree with evidence (`confirmed_by_bronze`, `corroborated`), the ontology, or an earlier instruction? Which wins?
   - **Names**: every table, column, or term that is not in bronze or the ontology. Typo, other schema, or business term?
   - **Scope and privacy**: tables or columns in review; personal data (keep, mask, hash, leave out).
   - **Impact**: which steps rerun and which checkpoints go back to pending. Is that scope right? Other sources too?
   - **Knowledge**: what does the person know that is not written down (meaning of a row, update cycle, who owns the data)?
4. Ask in chat. **Max 7 questions**, most important first, numbered. For each: one line why you ask and what it changes.
   Give options when there are clear choices. Accept "I don't know" and "skip".
5. Write `QZ-<CP>-nnn.answers.yaml` next to the questionnaire (format is in the questionnaire). Record as:
   - `instruction`: a rule for a step or all steps ("leave LOGIN_TS out", "use port local time")
   - `evidence`: a fact (team knowledge, medium confidence; `client_confirmed: true` only if the client said it)
   - `feedback`: a change to an output that needs a rerun
   - `question`: the person does not know -> a client question. Never guess an answer.
   - `none`: noted only
6. Run `python tools/x_clarify.py record <id> QZ-<CP>-nnn`. Show the person the result lines.
7. If the person does not want questions: `python tools/x_clarify.py skip <id> QZ-<CP>-nnn --reason "<their reason>"`.

## Rules
- Use the person's words in `answer`. Do not add facts they did not say.
- Do not re-ask what an active instruction or answered questionnaire already says.
- Plain, short English (ASD-STE100). No long explanations.
- Do not change STTM, code, or evidence yourself in this skill. The next step does that, using the recorded answers.
