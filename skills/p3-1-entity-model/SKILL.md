---
name: p3-1-entity-model
description: Step P3.1 (global). Propose new or changed shared master entities, business objects, relationships, and key normalisation rules for the central model, as a change request - never as a silent edit. Use when a source brings a business object, key format, or relationship that the registry or ontology does not cover, and before checkpoints CP3 and CP3b.
---

# P3.1 Central model (phase P3, global checkpoints CP3_central_model and CP3b_key_rules)

## Goal
Keep ONE coherent model for all ~30 sources: business objects (business ontology) -> data classes (data ontology) -> shared entities (registry).

## Inputs
- `registry/ontology/business.yaml`, `registry/ontology/data.yaml`
- `registry/entities.yaml`, `registry/key_normalisation.yaml`
- Source briefs and evidence registers that need a change (only the lines that matter)
- Open feedback in `registry/feedback/CP3_central_model/` and `registry/feedback/CP3b_key_rules/`

## Steps
1. Find the gap. Examples: a new business object; a new synonym; a new relationship; a shared code with a new format.
2. Check synonyms first. If the source word is a synonym of an existing object, add the synonym. Do not add a new object.
3. Write a change request from `templates/change_request.md` to `registry/change_requests/CR-<nnn>.md`:
   - business layer: object, kind, domain, definition, synonyms, relationships (with cardinality), rules;
   - data layer: data_class, history, load pattern;
   - registry: entity table name, business key, key rule, survivorship;
   - evidence ids from each source that supports it.
4. After approval in the PR, apply the change to the YAML files in the SAME PR.
5. Run `python tools/x_ontology_check.py`. It must print `ONTOLOGY COHERENT`.
6. Record the decision in `registry/decisions.md` (D-nnnn).

## Survivorship (CP3b)
When two or more sources map the same entity, add `survivorship.<Entity>` to `registry/key_normalisation.yaml`:
`default` (most_recent_update | source_priority), `source_priority`, and per-attribute `priority` lists where the business has a preferred source.
`tools/x_ontology_check.py` fails without it, and when the same column has different types in different sources.

## Rules
- Shared masters must use a `conformed` data class (master or reference).
- A synonym belongs to one object only.
- Every FK in any STTM must follow a relationship in `business.yaml`. Add the relationship here first.
- Changing an approved entity resets CP3 to `pending` and every STTM that uses it must be checked again.

## Checkpoint pack (last step of the phase)
Run `python tools/x_checkpoint_pack.py global --all`.
It writes `.xlsx`, `.json`, `.md`, and `.html` into the phase's `checkpoint/` folder. The reviewer opens the `.html` first.
Run it again after every change: the checkpoint check fails when the pack is stale.

## Done when
The ontology check passes and the data architect approves the PR (CP3 / CP3b).

## When the problem belongs to an earlier phase
Do not work around it. Raise it, and continue with the rest:
`python tools/x_feedback.py raise <id> <earlier CP> --step p3-1-entity-model --comment "..." --blocks CP3_central_model`
A person accepts or rejects it. Your checkpoint stays blocked until it is resolved.
