# Coding standard (PLACEHOLDER — replace with the client's guideline)

Keep this file short and testable. Genie Code reads it in the `pyspark-codegen` skill.
Where a rule can be checked by code, also add it to `standards/naming.yaml` or `lib/qa_checks.py`.

## Structure
- One notebook per target table: `nb_slv_<source_id>_<target_table>`.
- Cells in this order: parameters → imports → read → dedup → joins → columns → technical → load → QA.
- Parameters come from widgets (`catalog`, `silver_schema`, `batch_id`). No hard-coded catalog or schema names.

## Reuse
- Keys: `lib.keys.normalise`. Load: `lib.load_patterns.load`. QA: `lib.qa_checks`.
- Do not copy these functions into notebooks.

## Spark
- No `collect()` / `toPandas()` on large DataFrames.
- Use column expressions, not Python UDFs, unless no built-in function exists.
- Assert row counts after joins that must not multiply rows.

## Logging and errors
- Use the client logging helper (replace this line with its name). No bare `print`.
- Do not catch and hide exceptions. Fail the job and report.

## Comments
- Every derived column cites the STTM column it implements.
- Every business rule cites the sign-off file.
