---
name: p1-2-triage
description: Step P1.2. Classify each inventoried file of one source as core, supporting, background, or ignore, set its document type from the information ontology, and write a read plan (which sheets, pages, or sections) for core and supporting files. Use after p1-1-inventory and after feedback that changes which files to read.
---

# P1.2 Triage (phase P1, checkpoint CP1_source_brief)

## Goal
Decide WHAT to read and HOW MUCH, so later steps read a few precise parts and not the whole dump.

## Inputs (read only these)
- `sources/<id>/01_intake/manifest.md`
- `sources/<id>/01_intake/triage.yaml` (draft from P1.1)
- `registry/ontology/information.yaml` - `document_types`, `relevance`, `reading_rules`, `budgets`
- `registry/ontology/business.yaml` - the business objects named for this source in `registry/sources.yaml`
- Open feedback in `sources/<id>/01_intake/feedback/CP1_source_brief/`

## Steps
1. For each file in `triage.yaml`:
   - Check `doc_type`. Change it if the name, folder, or sheets show a better type.
   - Set `relevance` (see the table below). Give a short `reason`.
   - For `core` and `supporting`: write a `read_plan` (sheets / pages / sections + `why`). You may open the file ONLY to see its table of contents, sheet names, or headings.
   - Set `status: confirmed`.
2. Version groups and duplicates: keep ONE latest version. Mark the others `ignore` with reason "older version of IF-xxxx" or "duplicate of IF-xxxx".
3. Count the core files. Limit: `budgets.max_core_files`. Above the limit, move files to `supporting`, or ask for a `budget_override` by feedback.
4. Run `python tools/p1_2_check_context.py <id> --only triage`. Fix every error.
5. Log: `python tools/x_feedback.py log <id> p1-2-triage --note "<core>/<supporting>/<background>/<ignore>"`.

## Relevance guide
| Relevance | Use for | Read later? |
|---|---|---|
| core | data dictionary, schema, latest profiling workbook, overview, business rules for this source's business objects | yes, only `read_plan` parts |
| supporting | profiling HTML, interface spec, process deck, sample extract | only to fill a gap named in the brief |
| background | meeting notes, emails, chats | only when a person or a question points to it |
| ignore | old versions, duplicates, other systems, logos, templates | never |

## Feedback kinds you will see here
- `include_paths` - make these files core or supporting.
- `ignore_paths` - make these files ignore.
- `comment` - for example "sheet X has the real keys".
- `budget_override` request - only a person sets it in `triage.yaml`, with the feedback id.

## Template
`templates/triage_guidance.md` - examples of good read plans.

## Done when
`p1_2_check_context.py --only triage` passes and every line has `status: confirmed`.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p1-2-triage --comment "..." --blocks CP1_source_brief`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
