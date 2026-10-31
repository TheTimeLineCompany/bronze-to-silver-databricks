---
name: p2-3-evidence-reconcile
description: Step P2.3. Reconcile document claims, client profiling confidence, and bronze profiling results for one source into the evidence register - set status corroborated, confirmed_by_bronze, or contradicted, raise questions for conflicts, and update the source brief. Use after P2.1 and P2.2, and after CP2 feedback.
---

# P2.3 Evidence reconcile (phase P2, checkpoint CP2_evidence)

## Goal
Every fact that a key, FK, grain, or business rule will use has a clear status and enough confidence.

## Inputs
- `02_evidence/evidence_register.csv`, `01_intake/source_brief.md`
- `02_evidence/discovery/summary.md`, `tables.csv`, `links.csv` (filtered)
- `02_evidence/profiling/doc_profiles.csv` (filtered), `02_evidence/profiling/*.json` (targeted checks)
- `registry/ontology/information.yaml` - `confidence`, `confidence_rules`, `evidence_status`, `evidence_origins`
- Open feedback in `02_evidence/feedback/CP2_evidence/`

## Steps
0. Add the bronze facts from discovery: `python tools/p2_2_discover.py evidence <id>`.
1. For each claim the mapping will need:
   - Bronze confirms it -> `status: confirmed_by_bronze`, `corroborated_by: 02_evidence/discovery/<file>#<item>` or `02_evidence/profiling/<file>.json`.
   - A second independent document (authority <= 3) agrees -> `corroborated`, `corroborated_by: E-xxxx`.
   - Bronze contradicts it -> `contradicted`. Bronze wins for structure. Add a new bronze claim. Raise a question for MEANING.
   - Newer document replaces it -> `superseded`.
2. Add bronze facts as new lines: `origin: bronze_profile`, `location: 02_evidence/discovery/...` or `02_evidence/profiling/<file>.json`, confidence `high` (step 0 does this for discovery).
3. Low / unknown claims that a key, FK, grain, or business rule needs: verify in bronze, or raise a question (`blocking: true`). Write the question id in `notes`.
4. Feedback items:
   - `comment` / `answer` -> new evidence with `origin: client_answer` when it is a client answer, and link the question.
   - `include_paths` -> read only those files (the parts needed), add claims.
   - `data` -> use the P2.2 result for that table and filter.
   - Then set the feedback `applied`: `python tools/x_feedback.py set FB-xxxx applied --source <id> --summary "..." --changed <files>`.
5. Update `source_brief.md` (still within the word budget).
6. Run `python tools/p1_2_check_context.py <id>`. Fix every error.

## Templates
- `templates/evidence_register_template.csv` (`about_type`: table, column, grain, key, relationship, entity, business_rule, code_value, other)

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py <id> CP2_evidence`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## Done when
The context check passes, and no key / FK / business-rule claim is only low or unknown without a question.
A person then reviews at CP2 (PR). The gate needs discovery results (or targeted profiling results) and all discovery cards answered.

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p2-3-evidence-reconcile --comment "..." --blocks CP2_evidence`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
