# CP2_evidence - Evidence

Source: `S07_container_moves` · Phase: P2 · Status: **pending** · Approver: phase1-lead · Generated: 2026-10-31T11:41:50Z

Check that each fact the mapping needs has enough evidence, and that conflicts are handled.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Evidence claims | 23 |  |
| High / medium / low+unknown | 20 / 2 / 1 |  |
| Confirmed by bronze or corroborated | 19 |  |
| Contradicted | 0 |  |
| Client profiling rows | 9 | 2 low |
| Bronze tables | 9 | 1 staging |
| FK links found | 8 | 2 need a key rule |
| Agent cards answered | 6 / 7 |  |
| Table scope in / out / derive / review | 6 / 2 / 1 / 0 |  |
| Columns out of scope / in review | 7 / 0 | 4 app log, 2 audit, 0 secret |
| Personal-data columns | 3 | need privacy handling in the STTM |
| Unity Catalog metadata sections read | 1 / 9 | missing: tables, columns, tags, masks_and_filters, constraints, detail_history,  |
| Documents vs bronze gaps | 8 |  |

## Connections

*Tables in lineage order (level: table, role -> business object)*
- 0: carrier_contacts: master -> NEW:CarrierContact
- 0: container_types: reference -> NEW:ContainerType
- 0: locations: master -> Location
- 0: user_logins: technical -> -
- 1: containers: master -> Container
- 1: leg_daily_summary: aggregate -> none
- 1: shipments: transaction_header -> Shipment
- 2: legs: event -> ShipmentLeg
- -: legs_bkp_2025: staging -> -

*Bronze lineage: column -> referenced table (role), containment*
- `containers.TYPE_CD` N:1 (100%) -> `container_types (reference)` (fk)
- `leg_daily_summary.FROM_LOC` N:1 (100%) -> `locations (master)` (fk)
- `legs.CNTR_NO` N:1 (100%) -> `containers (master)` (fk)
- `legs.SHPMT_ID` N:1 (100%) -> `shipments (transaction_header)` (fk)
- `legs.FROM_LOC` N:1 (100%) -> `locations (master)` (fk)
- `legs.TO_LOC` N:1 (100%) -> `locations (master)` (fk)
- `shipments.ORIGIN_LOC` N:1 (100%) -> `locations (master)` (fk)
- `shipments.DEST_LOC` N:1 (100%) -> `locations (master)` (fk)

*Evidence claims by confidence (rows) and status (columns)*
| | unverified | corroborated | confirmed_by_bronze | contradicted | superseded |
|---|---|---|---|---|---|
| high | 3 | 0 | 17 | 0 | 0 |
| medium | 0 | 1 | 1 | 0 | 0 |
| low | 1 | 0 | 0 | 0 | 0 |
| unknown | 0 | 0 | 0 | 0 | 0 |

## Needs attention

- **error** `T-004`: discovery card not answered
- **error** `FB-0001`: feedback is 'open': blocks approval
- **error** `FB-0003`: upstream issue at CP1_source_brief (proposed) blocks this checkpoint: T-006: Brief says grain key CNTR_NO + SHPMT_ID + LEG_NO; bronze shows SHPMT_ID + LEG_NO is the minimal unique key (one container per shipment in this data). Con
- **warn** `user_logins`: no clear business object
- **warn** `E-0008`: low confidence, unverified; question Q-0001
- **info** `carrier_contacts`: proposes NEW:CarrierContact: needs a CP3 change request
- **info** `container_types`: proposes NEW:ContainerType: needs a CP3 change request
- **info** `legs.CNTR_NO`: values match only after normalisation: key rule needed (CP3b)
- **info** `legs.FROM_LOC`: values match only after normalisation: key rule needed (CP3b)

## Reviewer decides

- [ ] Are the table roles, grain keys, and business objects right (see lineage order)?
- [ ] Is the scope right: no logs, audit, or staging data in silver, and personal data handled?
- [ ] Is the evidence enough for every key, foreign key, grain, and business rule?
- [ ] Are contradictions resolved, with bronze for structure and documents for meaning?
- [ ] Are the open questions the right ones, and is 'blocking' set correctly?

## Files in this pack

- `CP2_evidence.xlsx` full lists: Column scope, Doc gaps, Bronze tables, Bronze links, Evidence, Bronze checks, Client profiling, Questions, Feedback, Upstream issues
- `CP2_evidence.json` machine-readable, for p4-1-sttm-author (reads evidence and bronze results)
- `CP2_evidence.html` one-page view

Give feedback: `python tools/x_feedback.py new S07_container_moves CP2_evidence --comment "..."`
