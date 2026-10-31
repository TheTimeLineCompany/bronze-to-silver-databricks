# Handoff readiness: <source_id> - <system name>

- **Prepared by:** <name>   **Date:** <YYYY-MM-DD>   **Commit:** <sha>
- **Checkpoints:** CP1 ✔  CP2 ✔  CP3 ✔  CP3b ✔  CP4 ✔  CP4b ✔/n.a.  CP5 ✔  CP6 in review
- **Business scope:** domain <DOM>, process <P-...>, business objects <...>

## Deliverables
| Item | Path |
|---|---|
| Approved STTM | `sources/<id>/04_mapping/sttm.yaml` (v...) |
| STTM workbook / ER | `sources/<id>/04_mapping/exports/sttm.xlsx`, `er.mmd` |
| Notebooks | `sources/<id>/05_build/nb_slv_...` |
| Job definition | `sources/<id>/05_build/job_slv_<id>.json` |
| QA evidence | `sources/<id>/05_build/qa_results/summary.json` |
| Reviews | `sources/<id>/04_mapping/reviews/sttm_review.md`, `business_logic_signoff.md`, `code_review.md` |
| Evidence | `sources/<id>/02_evidence/evidence_register.csv` |

## Target tables
| Table | Business object | Data class | Grain | Load pattern | Rows in dev | Depends on |
|---|---|---|---|---|---|---|

## Run order and schedule
<Masters first, then process tables. Suggested schedule and SLA.>

## Known limitations and non-blocking questions
| ID | Description | Impact | Owner |
|---|---|---|---|

## Feedback history
| FB id | Checkpoint | Summary | Status |
|---|---|---|---|

## Deployment notes
- Required grants: ...
- Parameters per environment: catalog, silver_schema
- Rollback: ...
