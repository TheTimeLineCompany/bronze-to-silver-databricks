---
name: p3-logical
description: Step P3 (central model, upgraded). Build the logical silver model (tables, grain, data class, PK, BK, FK, cardinality) from the conceptual model, the column understanding and the scope. Starts from a deterministic draft. Use when P2.3 is current, or when the conceptual model or scope changed.
---

# P3 Central model: logical silver model

## Steps
1. `python -m b2s draft-logical <app>` — a first draft from the conceptual model, the in-scope columns and the baseline keys (names from the ontology abbreviations, e.g. `cntr_no` → `container_no`).
2. Refine: grain sentences, data class per `_project/data.yaml`, business keys, FKs that follow ontology relationships, shared masters from `_project/entities.yaml`. Keep `source_hint` on mapped columns.
3. Mark status (`assumed` + `A-`, `unknown` + `Q-`). Save as a new version with a reason; `python -m b2s check <app>`.
4. Show the worker the logical view (`@x-model-view`): boxes, keys, cardinality.
5. Ask for **CP3** (`@x-approve`). It needs CP2 for the versions used (chain). **P4 cannot start before CP3.**

S3 joins (on in-scope tables only) stay as in V1.3; use their results for the relationships.
