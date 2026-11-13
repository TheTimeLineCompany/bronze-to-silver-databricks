---
name: x-research
description: Ask Glean in rounds, conceptual first and columns last, through request/reply files that work with the Glean connector or in paste mode. Use in P2.2b (conceptual) and P2.3 (columns marked unclear).
---

# @x-research — Glean rounds

Read `rules/glean.md` first.

## Steps
1. Write the topics as JSON: `[{"topic": "purpose", "question": "What business process does the yard application support?"}]` (column rounds add `"about": "<schema.table.column>"`).
2. `python -m b2s research new <app> conceptual --data topics.json --via genie` (types: conceptual, conceptual_followup, column). The CP1 Glean check (before an open point becomes a client question) uses the same round files. It prints the request text.
3. Send: Glean connector if available (`research sent <app> GR-nnnn --channel connector`), else show the text to the worker to paste into Glean (`--channel paste`).
4. **Save the raw reply first**, exactly as received: `python -m b2s research raw <app> GR-nnnn --data reply.txt --channel ...`
5. `python -m b2s research parse <app> GR-nnnn` (optionally `--data` with your reading as JSON).
6. Integrate claims as evidence: `python -m b2s research integrate <app> GR-nnnn --data claims.json --via genie` with `[{"statement": "...", "about": [...], "cites": "IF-0003"}]`. Use `cites` when Glean names a document of this application.
7. Update the brief and models; ask follow-up rounds for the gaps.
