# STTM examples (few-shot)

Two complete examples are in the repo. Read both before you write a new STTM.

## Example 1 - master entity with history
File: `sources/S01_buyer_master/04_mapping/sttm.yaml`

What it shows:
- `business_object: Buyer`, `data_class: master`, `target_kind: master`, `conformed_entity: Buyer`. Table name, business key, and SCD type are copied from `registry/entities.yaml`.
- `load_pattern: scd2` with `effective_from`, `effective_to`, `is_current` as `technical` columns.
- Surrogate key = hash of `buyer_id` + `effective_from`.
- A `lookup` column from the department table through a `left` join with cardinality `N:1`.
- A `derived` flag (`is_active`) with the code meaning cited by evidence id.
- A column that cites an answered question (`Q-0002`).

## Example 2 - event table with foreign keys
File: `sources/S07_container_moves/04_mapping/sttm.yaml`

What it shows:
- `business_object: ShipmentLeg`, `data_class: event`, `load_pattern: merge` (corrections arrive later).
- Grain: one row per container per leg. Business key of three columns; one is normalised with the `container_number` rule.
- FKs to shared masters (`Container`, `Location` twice), each `N:1` with `orphan_policy: unknown_member`. Each FK follows a relationship in `business.yaml` (R10, R11, R12).
- A column with **low confidence** and a **blocking** question (`eta_ts`, Q-0001). The STTM stays `draft` until the question is answered.
- A **business_logic** column (`transit_days`) with `business_rule: BR-LOGI-001` and the exact formula. This needs CP4b.

## Example 3 - composite foreign key (header / line, SAP style)
```yaml
- target: po_header_sk
  type: STRING
  nullable: false
  rule: lookup
  source: l.MANDT, l.EBELN
  transform: lookup slv_po_header on (client, po_number)
  key_role: FK
  fk:
    table: slv_po_header          # a target table in the same STTM (header loads first)
    column: po_header_sk          # its surrogate key
    cardinality: "N:1"
    orphan_policy: reject         # orphans go to <table>_quarantine; QA-01 accounts for them
    lookup_on: [l.MANDT, l.EBELN] # in the order of the header business key [client, po_number]
```
Discovery shows this as `ekpo.MANDT+EBELN -> ekko.MANDT+EBELN` in `02_evidence/discovery/links.csv`.

## Why each choice (reasoning to copy)
| Situation | Choice | Reason |
|---|---|---|
| Document says "CNTR_NO is the container"; profiling shows spaces and dashes | `rule: normalised_key`, `key_rule: container_number` | Keys must match the Container master from other sources. |
| Location codes come in mixed case | lookup on `keys.normalise('generic_code', ...)` | Same rule as the Location master, so the join finds the parent. |
| Two date formats in one column, time zone unknown | `confidence: low` + blocking question | A wrong time zone shifts every ETA. Do not guess. |
| KPI defined in a document | `business_logic: true` + `business_rule` + exact formula | The client must sign off how KPIs are calculated (CP4b). |
| Client workbook says "Low" for a key column, bronze shows it unique | cite the bronze evidence (`confirmed_by_bronze`) | Bronze decides structure. |
| A column 55% null with unknown meaning | leave it out; write it under "Not used" in the brief | Do not map what nobody can explain. |
