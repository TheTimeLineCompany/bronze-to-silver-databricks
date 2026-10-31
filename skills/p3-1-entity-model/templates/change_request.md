# CR-<nnn>: <short title>

- Raised by: <name>   Date: <yyyy-mm-dd>   Sources: <S07_..., S12_...>
- Checkpoint: CP3_central_model | CP3b_key_rules
- Feedback: FB-xxxx (if any)

## 1. Why
<The gap, in two or three sentences. Cite evidence: S07 E-0005, S12 E-0011.>

## 2. Business layer (registry/ontology/business.yaml)
| Item | Change |
|---|---|
| business object | <Name> (kind: party/thing/place/event/agreement/measure/classification, domain: <DOM>) |
| definition | <one sentence> |
| synonyms | <words used in sources> |
| relationships | R<nn> <Object> <verb> <Object> (N:1) |
| business rules | BR-<DOM>-<nnn> <one line> |

## 3. Data layer (registry/ontology/data.yaml + registry/entities.yaml)
| Item | Value |
|---|---|
| data_class | master / reference / ... |
| table | slv_mst_<name> |
| business key | <cols>, key rule <rule> |
| history | SCD2 / SCD1 |
| survivorship | which source wins for which attribute |

## 4. Impact
- STTMs to re-check: <list>
- Checkpoints reset: CP3 (global) -> CP4 of: <sources>

## 5. Decision
Result: APPROVED / REJECTED   By: <data architect>   Date:   Decision id: D-<nnnn>
