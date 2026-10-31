# CP2_evidence - Evidence

Source: `S01_buyer_master` · Phase: P2 · Status: **pending** · Approver: phase1-lead · Generated: 2026-10-31T11:41:51Z

Check that each fact the mapping needs has enough evidence, and that conflicts are handled.

## Key numbers

| Item | Value | Note |
|---|---|---|
| Evidence claims | 5 |  |
| High / medium / low+unknown | 4 / 1 / 0 |  |
| Confirmed by bronze or corroborated | 3 |  |
| Contradicted | 0 |  |
| Client profiling rows | 7 | 0 low |

## Connections

*Evidence claims by confidence (rows) and status (columns)*
| | unverified | corroborated | confirmed_by_bronze | contradicted | superseded |
|---|---|---|---|---|---|
| high | 2 | 1 | 1 | 0 | 0 |
| medium | 0 | 0 | 1 | 0 | 0 |
| low | 0 | 0 | 0 | 0 | 0 |
| unknown | 0 | 0 | 0 | 0 | 0 |

## Needs attention

- **error** `bronze`: no bronze results: run tools/p2_2_discover.py

## Reviewer decides

- [ ] Are the table roles, grain keys, and business objects right (see lineage order)?
- [ ] Is the scope right: no logs, audit, or staging data in silver, and personal data handled?
- [ ] Is the evidence enough for every key, foreign key, grain, and business rule?
- [ ] Are contradictions resolved, with bronze for structure and documents for meaning?
- [ ] Are the open questions the right ones, and is 'blocking' set correctly?

## Files in this pack

- `CP2_evidence.xlsx` full lists: Evidence, Bronze checks, Client profiling, Questions, Feedback
- `CP2_evidence.json` machine-readable, for p4-1-sttm-author (reads evidence and bronze results)
- `CP2_evidence.html` one-page view

Give feedback: `python tools/x_feedback.py new S01_buyer_master CP2_evidence --comment "..."`
