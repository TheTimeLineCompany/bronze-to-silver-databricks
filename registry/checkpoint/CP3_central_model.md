# CP3_central_model - Central model

Source: `global` · Phase: P3 · Status: **pending** · Approver: data-architect · Generated: 2026-10-31T11:41:52Z

Check the shared business objects, relationships, and master entities for all sources.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Business objects | 15 |  |
| Relationships | 17 |  |
| Entities approved / proposed | 0 / 6 |  |
| Key rules | 5 |  |
| Business rules | 3 |  |

## Connections

*Business relationships (subject - verb - object, cardinality)*
- `Buyer` belongs_to (N:1) -> `Department` (R01)
- `Buyer` manages (1:N) -> `Supplier` (R02)
- `PartMaterialContent` of_part (N:1) -> `Part` (R03)
- `PartMaterialContent` of_material (N:1) -> `Material` (R04)
- `MaterialIndex` for_material (N:1) -> `Material` (R05)
- `PartPrice` for_part (N:1) -> `Part` (R06)
- `PartPrice` from_supplier (N:1) -> `Supplier` (R07)
- `Part` bought_by (N:1) -> `Buyer` (R08)
- `ShipmentLeg` part_of (N:1) -> `Shipment` (R09)
- `ShipmentLeg` moves (N:1) -> `Container` (R10)
- `ShipmentLeg` departs_from (N:1) -> `Location` (R11)
- `ShipmentLeg` arrives_at (N:1) -> `Location` (R12)
- `SavingsTarget` for_initiative (N:1) -> `SavingsInitiative` (R13)
- `SavingsActual` for_initiative (N:1) -> `SavingsInitiative` (R14)
- `SavingsInitiative` concerns_part (N:1) -> `Part` (R15)
- `SavingsInitiative` concerns_supplier (N:1) -> `Supplier` (R16)
- `SavingsInitiative` owned_by (N:1) -> `Buyer` (R17)

## Needs attention

- **warn** `ontology`: business object PartMaterialContent is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object MaterialIndex is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object PartPrice is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object Shipment is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsInitiative is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsTarget is not yet covered by any source, entity, or STTM
- **warn** `ontology`: business object SavingsActual is not yet covered by any source, entity, or STTM
- **warn** `ontology`: survivorship Part: source S03_part_catalogue is not in registry/sources.yaml (yet)
- **info** `Part`: entity not yet approved
- **info** `Supplier`: entity not yet approved
- **info** `Buyer`: entity not yet approved
- **info** `Material`: entity not yet approved
- **info** `Location`: entity not yet approved
- **info** `Container`: entity not yet approved

## Reviewer decides

- [ ] Does each business object have one clear definition, and are the synonyms right?
- [ ] Is every relationship true for the business, with the right cardinality?
- [ ] Is each shared entity a master or reference, with the right business key and history?

## Files in this pack

- `CP3_central_model.xlsx` full lists: Entities, Key rules, Business objects, Relationships, Business rules, Feedback
- `CP3_central_model.json` machine-readable, for p4-1-sttm-author for every source
- `CP3_central_model.html` one-page view

Give feedback: `python tools/x_feedback.py new global CP3_central_model --comment "..."`
