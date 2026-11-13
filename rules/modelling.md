# Modelling

Linked from `AGENTS.md` rules 6 and 7. Design: `docs/V1_4_DESIGN.md` §9.

## Models (YAML is the truth; Mermaid and HTML are generated)
| Model | Shows | Mermaid |
|---|---|---|
| dependencies | direct upstream and downstream systems of this application | flowchart |
| process | the work that happens, its steps, and the tables that record each step | flowchart |
| conceptual | business objects of the ontology and their relationships | flowchart |
| logical | silver tables: grain, data class, PK, BK, FK, cardinality | erDiagram |
| mapping | business object → silver table → bronze id columns, with key rules | flowchart |

## Rules
- Use the business object NAME from `_project/business.yaml`. Source words go into synonyms by change request.
- A new object, relationship or rule is a change request (`CR-`); until the project ontology owner accepts it, it is `assumed` in the application.
- Every element has `status`: known, assumed (with `assumption: A-nnnn`), unknown (with `question: Q-nnnn`). The validator checks this.
- Logical model: each table states `business_object`, `data_class`, `grain` (one sentence), `primary_key`; FKs are 1:1, 1:N or N:1 (resolve N:M with a bridge table).
- Bronze wins for structure (keys, nulls, formats). Documents win for meaning. A client answer wins for both.
- After saving a model, run `@x-model-view`; the HTML must match the Mermaid.
