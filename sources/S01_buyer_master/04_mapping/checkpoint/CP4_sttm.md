# CP4_sttm - Source-to-target mapping

Source: `S01_buyer_master` · Phase: P4 · Status: **pending** · Approver: phase1-lead · Generated: 2026-10-31T11:41:51Z

Check the mapping from bronze to silver, column by column, back to evidence.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Target tables | 1 |  |
| Columns | 8 |  |
| Foreign keys | 0 |  |
| Business-logic columns | 0 | need CP4b |
| Low / unknown confidence | 0 |  |
| Validator | PASS | 0 errors, 0 warnings |
| Independent review | missing |  |

## Connections

*Business object -> silver table -> shared masters (relationship id)*
- `Buyer` is stored as -> `slv_mst_buyer (master, scd2)`

## Needs attention

- **info** `review`: sttm_review.md: missing

## Reviewer decides

- [ ] Is the grain right, and is the business key unique in bronze?
- [ ] Does each foreign key follow a real business relationship?
- [ ] Are the transforms exact, and does each column cite good evidence?

## Files in this pack

- `CP4_sttm.xlsx` full lists: Tables, Columns, Foreign keys, Questions, Feedback
- `CP4_sttm.json` machine-readable, for Handover H1 (with CP4b) -> p5-1-pyspark-codegen
- `CP4_sttm.html` one-page view

Give feedback: `python tools/x_feedback.py new S01_buyer_master CP4_sttm --comment "..."`
