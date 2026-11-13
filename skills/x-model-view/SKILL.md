---
name: x-model-view
description: Build the interactive HTML view of a model version (dependencies, process, conceptual, logical, mapping) and check that it matches the Mermaid file. Use after a model YAML gets a new version, before an approval request, or when the worker asks to "see" a model.
---

# @x-model-view — model viewer that matches the Mermaid

## When to run
- A model YAML got a new version (`models/<name>.vNNN.yaml`).
- Before `python -m b2s approve request` (approval pages embed the viewer; the request refuses to run if the check fails).
- The worker asks to see the entities, tables, keys or mappings.

## Command
```
python -m b2s view <app> [model] [version]
```
- `model`: dependencies | process | conceptual | logical | mapping (default: all that exist)
- `version`: for example `v004` (default: latest)

It writes, next to the YAML version:
- `<model>.vNNN.mmd` — the Mermaid. This is the accountability record.
- `<model>.vNNN.html` — one self-contained page: boxes that never overlap, keys (PK, FK, BK), cardinality as crow's-foot ends, as text ("N:1 — many slv_shipment_leg, one slv_shipment") and as Mermaid notation (`}o--||`), a Mermaid tab with the exact source, click / filter / search / zoom.

## What the check means
`check-views` compares three things: the model YAML, the `.mmd`, and the graph stored inside the `.html`.
They must have the same boxes, labels, statuses, columns and keys, and the same relationships with the same cardinality.
- **Pass:** report the link to the `.html`.
- **Fail:** report the exact differences. Do not continue to an approval.

## Rules
- Never edit a `.mmd` or `.html` by hand. Change the YAML and save it as a new version (`python -m b2s save`), then run this skill again.
- Status is shown by shape and text, not only colour: unknown = `?` and a red dashed border; assumed = dashed border and the `A-` id.
- Show the worker the link and a one-line summary (tables, relationships, unknown and assumed counts). Do not paste the HTML into the chat.
