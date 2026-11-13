---
name: p2-2b-understand
description: Step P2.2b (new in V1.4, inside P2). Understand what the application does for the business - from the bronze baseline, the documents and Glean conceptual rounds together - and build the app brief, the app dependencies model, the process model and the conceptual model, marking unknowns with ? and assumptions with A- ids. Use after P2.2, and again when new input arrives.
---

# P2.2b Application understanding and models

These are the backend tables of an application. Find out what happens in it from a business point of view and what it
depends on. This is the base for the central model (P3) and the silver design. Where neither the tables nor the
documents make it clear, mark `?` and continue. Read `rules/modelling.md` and `rules/glean.md`.

## 1. Understand
1. From the baseline: group the tables (masters, transactions, lines, logs, copies); note what the names suggest about the work.
2. From the documents and the P2.2 comparison: workflows, flowcharts, systems named.
3. **Glean, conceptual round** (`@x-research`): what does the application do, which work happens in it, which systems send it data and receive data from it. No column questions yet. Integrate the answers as evidence; ask follow-up conceptual rounds for gaps.
4. Write `understanding/app_brief.md` (≤ 1800 words): purpose, users, processes, dependencies, tables per process, what is not clear. Cite `E-` ids. Unclear → `Q-` (or `A-` if you proceed on an assumption).

## 2. Model (formats: `docs/V1_4_DESIGN.md` §9.1–9.3, examples `tests/fixtures_models.py`)
5. `models/dependencies.yaml` — direct upstream and downstream systems only.
6. `models/process.yaml` — processes (link `business_process` to `_project/business.yaml`), steps, flows, the tables that record each step.
7. `models/conceptual.yaml` — business objects of the ontology this application uses, the tables behind each, relationships with verb and cardinality. A new object or relationship → change request `CR-`.
8. Every element has `status`: known, assumed (+ `A-` item), unknown (+ `Q-` item).

## 3. Save and show
9. Save each file: `python -m b2s save <app> <stem> <file> --reason "..." --via genie` (stems: `understanding/app_brief`, `models/dependencies`, `models/process`, `models/conceptual`). Invalid models are refused; views are written.
10. `python -m b2s check <app>`; show the worker the HTML views (`@x-model-view`).

Then `@p2-3-scope`. CP2 is asked after the scope proposal.
