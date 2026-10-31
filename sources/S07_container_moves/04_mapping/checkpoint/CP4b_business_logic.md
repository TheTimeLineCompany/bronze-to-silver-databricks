# CP4b_business_logic - Business logic

Source: `S07_container_moves` · Phase: P4 · Status: **pending** · Approver: client-sme · Generated: 2026-10-31T11:41:50Z

The business expert checks each calculated value and its formula.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Business-logic columns | 1 |  |
| Rules still 'proposed' | 1 |  |
| SME sign-off | missing |  |

## Connections

*Business rule -> silver column -> formula*
- `BR-LOGI-001` computes -> `slv_cnt_shipment_leg.transit_days` ((l.ATA_TS - l.ATD_TS) / 86400.0)

## Needs attention

- **info** `BR-LOGI-001`: rule is 'proposed' in business.yaml; set 'approved' with the sign-off

## Reviewer decides

- [ ] Is each formula the one the business uses (units, rounding, time zone)?
- [ ] Are the inputs the right fields?
- [ ] Who owns each rule after go-live?

## Files in this pack

- `CP4b_business_logic.xlsx` full lists: Business logic, Questions, Feedback
- `CP4b_business_logic.json` machine-readable, for Handover H1 -> p5-1-pyspark-codegen
- `CP4b_business_logic.html` one-page view

Give feedback: `python tools/x_feedback.py new S07_container_moves CP4b_business_logic --comment "..."`
