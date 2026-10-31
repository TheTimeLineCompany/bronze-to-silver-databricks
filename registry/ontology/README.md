# Ontology: three layers, one chain

The ontology is the fixed vocabulary of the project. It makes 30 sources give ONE coherent silver model,
and it keeps agents precise when a source dump holds hundreds of files.

| Layer | File | Question it answers | Owner |
|---|---|---|---|
| 1 Business | `business.yaml` | What does the business talk about? | data architect + client SMEs (CP3) |
| 2 Data | `data.yaml` | How is each business object stored in bronze and silver? | data architect (CP3) |
| 3 Information | `information.yaml` | Where does each fact come from, and how far can we trust it? | project lead |

## 1. Business layer (`business.yaml`)
| Element | Example | Rule |
|---|---|---|
| domain | LOGI Logistics | each process and object belongs to one domain |
| process | P-LOGI-02 Track container leg events | lists the objects it creates (C) and uses (U) |
| business object | ShipmentLeg (kind: event) | one name; source words go into `synonyms` |
| synonym | leg, segment, hop | belongs to ONE object only |
| relationship | R10 ShipmentLeg moves Container (N:1) | every silver FK must follow one |
| business rule | BR-LOGI-001 transit days = arrival - departure | every business-logic column cites one; signed off at CP4b |

## 2. Data layer (`data.yaml`)
| Element | Example | Rule |
|---|---|---|
| data class | master, reference, event, agreement, measure, snapshot, bridge | each silver table declares one |
| business kinds | event class fits kind `event` | class must fit the object's kind |
| allowed load patterns | event -> append, merge | the STTM load pattern must be in the list |
| conformed | master, reference = true | conformed classes are shared entities in `registry/entities.yaml` |
| key types | BK, SK, FK, PK_FK | FK = surrogate key of a conformed entity |
| grain rule | "One row per <object> per <qualifier>" | every table states its grain |

## 3. Information layer (`information.yaml`)
| Element | Example | Rule |
|---|---|---|
| document type | profiling_workbook (authority 3) | each inbox file gets one at triage |
| relevance | core / supporting / background / ignore | only core and supporting are read, only their read plan |
| budgets | 15 core files, 1800-word brief, 40-word claim | checked by `tools/p1_2_check_context.py` |
| evidence origin | document, bronze_profile, client_answer | bronze wins for structure, documents for meaning |
| confidence | high / medium / low / unknown | keys and business logic need more than low |
| evidence status | unverified -> corroborated / confirmed_by_bronze / contradicted / superseded | |
| phases, checkpoints, handovers | P0-P6, CP1-CP6 (+CP3b, CP4b), H1, H2 | checked by `tools/x_validate_gate.py` |

## 4. The chain (lineage) for every silver column
```
business object      business.yaml         ShipmentLeg
  -> silver table    sttm.yaml + data.yaml slv_cnt_shipment_leg (event, merge)
  -> silver column   sttm.yaml             container_sk  (FK -> Container via R10)
  -> bronze column   sttm.yaml source      legs.CNTR_NO
  -> evidence        evidence_register.csv E-0001, E-0002 (high, confirmed_by_bronze)
  -> origin          manifest / 02_evidence/profiling IF-0004 sheet LEGS row 4; 02_evidence/profiling/legs.json
```
If one link is missing, a check fails.

## 5. Which tool checks what
| Check | Tool |
|---|---|
| Domains, processes, synonyms, relationships, rules, entities, sources are consistent | `tools/x_ontology_check.py` |
| Each STTM table: business object, data class, load pattern, FK relationships, BR ids, evidence, confidence | `tools/p4_2_validate_sttm.py` |
| Triage, brief, and evidence register follow the information layer | `tools/p1_2_check_context.py` |
| Checkpoint order, evidence files, open feedback | `tools/x_validate_gate.py` |

## 6. How to change it
Only by change request (`@p3-1-entity-model`, `registry/change_requests/CR-nnn.md`) in a PR.
A change to an approved object or relationship sets CP3 back to pending and re-opens CP4 of the sources that use it.
