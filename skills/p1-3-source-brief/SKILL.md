---
name: p1-3-source-brief
description: Step P1.3. Read only the triaged core files of one source (only the parts in their read plans) and write a short source brief plus the first atomic evidence claims, each with origin, location, and confidence. Use after p1-2-triage, and after CP1 feedback.
---

# P1.3 Source brief (phase P1, checkpoint CP1_source_brief)

## Goal
One short page that tells every later step what this source IS, in business and data terms, with every fact traceable.

## Inputs (read only these)
- `01_intake/triage.yaml` - files with `relevance: core`, only the `read_plan` parts.
- `registry/ontology/business.yaml` - business objects, synonyms, processes, rules.
- `registry/ontology/data.yaml` - data classes.
- `registry/sources.yaml` - the domains, processes, and business objects listed for this source.
- Open feedback in `01_intake/feedback/CP1_source_brief/`.

## Steps
1. Read each core file part in its `read_plan`. One file at a time.
2. For each fact you need, add ONE line to `02_evidence/evidence_register.csv` (template: `../p2-3-evidence-reconcile/templates/evidence_register_template.csv`):
   - one claim, max `budgets.evidence_claim_max_words` words;
   - `origin: document`, `file_id`, `location` (sheet + row, page, or section), `doc_type`;
   - `confidence` from the document (a column in a profiling workbook) or `medium` if the document gives none;
   - `status: unverified`.
3. Map source words to the ontology: use the business object NAME, not the source's word. Use the synonyms in `business.yaml`. If no object fits, write a question; do not invent an object.
4. Write `01_intake/source_brief.md` from `templates/source_brief.md`. Max `budgets.source_brief_max_words` words. Every fact cites an evidence id `(E-0001)`.
5. Write unclear points as questions in `registry/open_questions.yaml` (`blocking: true` if a key, grain, or business rule depends on it).
6. Run `python tools/p1_2_check_context.py <id>`. Fix every error.
7. Log the run with `tools/x_feedback.py log`.

## Rules
- Do not read `supporting` or `background` files here unless open feedback tells you to.
- Do not copy long text. Summarise and cite.
- A low-confidence fact is a hypothesis. Write it as such in the brief.

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py <id> CP1_source_brief`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## Done when
The context check passes. A person then reviews the brief at CP1 (PR).

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p1-3-source-brief --comment "..." --blocks CP1_source_brief`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
