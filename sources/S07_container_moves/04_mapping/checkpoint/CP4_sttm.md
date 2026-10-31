# CP4_sttm - Source-to-target mapping

Source: `S07_container_moves` · Phase: P4 · Status: **pending** · Approver: phase1-lead · Generated: 2026-10-31T11:41:50Z

Check the mapping from bronze to silver, column by column, back to evidence.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Target tables | 1 |  |
| Columns | 10 |  |
| Foreign keys | 3 |  |
| Business-logic columns | 1 | need CP4b |
| Low / unknown confidence | 1 |  |
| Validator | PASS | 0 errors, 1 warnings |
| Independent review | missing |  |

## Connections

*Business object -> silver table -> shared masters (relationship id)*
- `ShipmentLeg` is stored as -> `slv_cnt_shipment_leg (event, merge)`
- `slv_cnt_shipment_leg` container_sk N:1 -> `Container` (R10)
- `slv_cnt_shipment_leg` origin_location_sk N:1 -> `Location` (R11 | R12)
- `slv_cnt_shipment_leg` destination_location_sk N:1 -> `Location` (R11 | R12)

## Needs attention

- **error** `Q-0001`: blocking question open: LEGS.ETA_TS has two formats (epoch seconds and 'DD/MM/YYYY HH24:MI'). Which time zone does the text format use?
- **warn** `slv_cnt_shipment_leg.eta_ts`: low confidence; question Q-0001
- **info** `review`: sttm_review.md: missing

## Reviewer decides

- [ ] Is the grain right, and is the business key unique in bronze?
- [ ] Does each foreign key follow a real business relationship?
- [ ] Are the transforms exact, and does each column cite good evidence?

## Files in this pack

- `CP4_sttm.xlsx` full lists: Tables, Columns, Foreign keys, Questions, Feedback
- `CP4_sttm.json` machine-readable, for Handover H1 (with CP4b) -> p5-1-pyspark-codegen
- `CP4_sttm.html` one-page view

Give feedback: `python tools/x_feedback.py new S07_container_moves CP4_sttm --comment "..."`
