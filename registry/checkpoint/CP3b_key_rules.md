# CP3b_key_rules - Key rules

Source: `global` · Phase: P3 · Status: **pending** · Approver: data-architect · Generated: 2026-10-31T11:41:52Z

Check the key formats and which source wins for shared attributes.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Business objects | 15 |  |
| Relationships | 17 |  |
| Entities approved / proposed | 0 / 6 |  |
| Key rules | 5 |  |
| Business rules | 3 |  |

## Connections

*Key rule -> shared entity that uses it*
- `part_number` normalises -> `Part`
- `supplier_code` normalises -> `Supplier`
- `buyer_id` normalises -> `Buyer`
- `container_number` normalises -> `Container`
- `generic_code` normalises -> `Material, Location`

## Needs attention

- **warn** `ontology`: business object PartMaterialContent is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object MaterialIndex is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object PartPrice is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object Shipment is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsInitiative is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsTarget is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsActual is not yet covered by any source, entity, or STTM
- **warn** `ontology`: survivorship Part: source S03_part_catalogue is not in registry/sources.yaml (yet)

## Reviewer decides

- [ ] Does each rule produce the same key from every source format?
- [ ] Is the pattern strict enough to catch bad keys?
- [ ] Is survivorship (which source wins) agreed for shared attributes?

## Files in this pack

- `CP3b_key_rules.xlsx` full lists: Entities, Key rules, Feedback
- `CP3b_key_rules.json` machine-readable, for p4-1-sttm-author, lib/keys.py
- `CP3b_key_rules.html` one-page view

Give feedback: `python tools/x_feedback.py new global CP3b_key_rules --comment "..."`
