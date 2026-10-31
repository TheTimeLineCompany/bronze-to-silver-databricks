# CP4b_business_logic - Business logic

Source: `S01_buyer_master` · Phase: P4 · Status: **not_required** · Approver: client-sme · Generated: 2026-10-31T11:41:51Z

The business expert checks each calculated value and its formula.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Business-logic columns | 0 |  |
| Rules still 'proposed' | 0 |  |
| SME sign-off | missing |  |

## Connections

*Business rule -> silver column -> formula*

## Needs attention

- **info** `scope`: no business-logic columns: CP4b can be 'not_required'

## Reviewer decides

- [ ] Is each formula the one the business uses (units, rounding, time zone)?
- [ ] Are the inputs the right fields?
- [ ] Who owns each rule after go-live?

## Files in this pack

- `CP4b_business_logic.xlsx` full lists: Business logic, Questions, Feedback
- `CP4b_business_logic.json` machine-readable, for Handover H1 -> p5-1-pyspark-codegen
- `CP4b_business_logic.html` one-page view

Give feedback: `python tools/x_feedback.py new S01_buyer_master CP4b_business_logic --comment "..."`
