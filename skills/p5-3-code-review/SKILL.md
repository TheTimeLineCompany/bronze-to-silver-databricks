---
name: p5-3-code-review
description: Step P5.3. Review the generated and completed notebooks against the approved STTM and the coding standards, in a NEW chat (never review your own work in the same chat), and write the review with a verdict. Use after P5.2 QA passed.
---

# P5.3 Code review (new chat)

## Read
`build/index` (notebook versions, run order), each notebook version it lists, the approved STTM (`sttm/sttm` at the CP4 version), `standards/coding.md`, `qa/results`.

## Check
- Every TODO(genie) cell does what the STTM says: filters, dedup, derived columns, business rules (cite the rule id).
- `bronze_count` is the row count after filter + dedup; no row is lost or duplicated by a join.
- No GENERATED cell was changed; no REVIEW block is left.
- Keys use `lib.keys.normalise`; foreign keys use `lib.keys.lookup_sk`; no own trim/upper/lpad.
- Personal-data columns follow the privacy handling of CP2; no value of a sensitive column is printed or written.
- Writes go to the dev silver schema only.

## Write
`build/code_review.md`, saved with `python -m b2s save <app> build/code_review <file> --reason "review" --via genie`:
```
# Code review — <app>
Index: build/index.vNNN
Verdict: pass            (or: Verdict: changes needed)
## Findings
- <notebook>: <finding> -> <what to change>
```
CP5 passes only with `Verdict: pass` on a review of the current index. Then `python -m b2s cp-auto <app> CP5`.
