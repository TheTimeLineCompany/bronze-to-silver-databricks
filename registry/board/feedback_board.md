# feedback_board - Feedback and upstream issues

Source: `all sources` · Phase: X · Status: **4 unresolved** · Approver: each item's checkpoint approver · Generated: 2026-10-31T11:41:53Z

All human feedback and all agent-raised upstream issues, with what each one blocks.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Items | 4 |  |
| Proposed by agents (to triage) | 3 | accept or reject |
| Open / in progress / applied | 1 / 0 / 0 |  |
| Verified / rejected | 0 / 0 |  |

## Connections

*Who raised it -> at which checkpoint (status) -> what it blocks*
- `agent:p2-2-bronze-discovery` FB-0002 proposed -> `global CP3_central_model`
- `agent:p2-2-bronze-discovery` FB-GLB-n9xw proposed -> `global CP3_central_model`
- `agent:p2-2-bronze-discovery` FB-0003 proposed -> `S07_container_moves CP1_source_brief` (blocks CP2_evidence)
- `reviewer1` FB-0001 open -> `S07_container_moves CP2_evidence`

## Needs attention

- **warn** `FB-0002`: proposed by agent:p2-2-bronze-discovery at CP3_central_model: a person must accept or reject
- **warn** `FB-GLB-n9xw`: proposed by agent:p2-2-bronze-discovery at CP3_central_model: a person must accept or reject
- **warn** `FB-0003`: proposed by agent:p2-2-bronze-discovery at CP1_source_brief: a person must accept or reject

## Reviewer decides

- [ ] Accept or reject each proposed item.
- [ ] Verify each applied item.
- [ ] Stop loops: decide items that came back a third time.

## Files in this pack

- `feedback_board.xlsx` full lists: Items
- `feedback_board.json` machine-readable, for x-feedback-rerun
- `feedback_board.html` one-page view

Give feedback: `python tools/x_feedback.py new all sources feedback_board --comment "..."`
