# Bronze discovery - methods and sources

This skill does not invent its own method. It uses established data-profiling and dimensional-modelling
practice, scaled down so that an agent pipeline can run it on ~30 source systems with fixed budgets.

## 1. Sources
| Topic | Source | What we take |
|---|---|---|
| Profiling tasks | Abedjan, Golab, Naumann: "Profiling relational data: a survey", VLDB Journal 24(4), 2015; and the book *Data Profiling* (Abedjan, Golab, Naumann, Papenbrock), Synthesis Lectures on Data Management, Morgan & Claypool / Springer, 2018 | The three classes: single-column, multi-column, dependencies. Keys = unique column combinations (UCC). Foreign keys = ranked inclusion dependencies (IND). |
| Key discovery | HCA and DUCC (Heise et al., VLDB 2013), described in the survey | Bottom-up Apriori search; prune by distinct counts; never test a superset of a found key. |
| Inclusion dependencies | SPIDER (Bauckmann et al., 2006); partial INDs (survey sec. 5) | Containment of distinct value sets; partial IND confidence = matched distinct values / distinct values. |
| FK ranking | Rostin et al., "A machine learning approach to foreign key discovery", WebDB 2009; Zhang et al., "On multi-column foreign key discovery", VLDB 2010 | Referenced side is a key; name similarity; dependent values look like a sample of the key; surrogate auto-increment ids give false INDs. |
| Grain and roles | Kimball & Ross, *The Data Warehouse Toolkit*, 3rd ed., Wiley 2013 (ch. 1-3: declare the grain; facts, dimensions, bridge, aggregate, snapshot) | Grain as one sentence; transaction / periodic snapshot / accumulating tables; aggregates are derived and rebuilt, not mastered. |
| Per-table checklist | `profiling-tables` agent skill, astronomer/agents (Apache-2.0) | Metadata first; statistics by type; top-20 values for categorical columns; quality dimensions. |
| Unity Catalog metadata | Databricks docs: `information_schema` (TABLES, COLUMNS, TABLE_TAGS, COLUMN_TAGS, TABLE_CONSTRAINTS, KEY_COLUMN_USAGE, REFERENTIAL_CONSTRAINTS, ROW_FILTERS, COLUMN_MASKS); `DESCRIBE DETAIL` / `DESCRIBE HISTORY`; `SHOW STATISTICS ... AS JSON` | Comments, owners, tags, masks; declared (informational) keys tried first; exact distinct/null counts when collected; writers and change data feed. |
| Lineage | Databricks docs: lineage system tables `system.access.table_lineage`, `system.access.column_lineage` | Who writes and reads each table (job, pipeline, notebook); tables outside the schema that feed this source; derived-from edges. |
| Sensitive data | Databricks data classification (Unity Catalog tags `class.*`), column masks | A classification tag or a mask marks a column as personal data even when its name and values do not. |

## 2. Pipeline and why each step is cheap
| Stage | Work | Cost control |
|---|---|---|
| catalog | table list, row counts, columns, types (+ `extra_tables` accepted from R-cards) | metadata only |
| meta | Unity Catalog sections above; each section returns `available: false` with the reason when a view or privilege is missing | metadata only |
| profile | per column: null %, approx distinct (HyperLogLog), min/max, lengths; shapes (A/9 pattern) for key-like strings; top values for low-cardinality columns | sample of `sample_rows`; caps on pattern and top-k columns |
| keys | single-column keys, then composite keys (size <= 3) from a pruned pool | exact full-table check ONLY for candidates; product of distinct counts must reach the row count; minimality pruning; `max_key_checks` |
| plan-links | candidate pairs dep.col -> ref.key | referenced side must be a key; type, distinct-count, range, and name filters; `max_link_checks` |
| links | containment raw and after normalisation (trim/upper/no spaces or dashes), reverse coverage, missing examples; single-column AND composite (n-ary) links | dependent side may be sampled (a subset of an FK is still contained); distinct sets only; composite candidates only from components with similar names (`composite_min_name_score`), best `composite_options` per component, `max_composite_link_checks` |
| model | roles, grain, lineage levels, derived-from (also from column lineage), ontology mapping, shared code domains, table scope, column classes, doc gaps, overlap with other sources | pure code on summaries |
| wider | related tables outside the schema (name tokens, shared key column names, lineage) | one query on `system.information_schema.columns`; `max_related` |
| cards | T-cards (one table decision), R-cards (related table: include?), D-001 (documented, not in bronze) | only where code confidence is not high |

## 2b. Column classes: name + content + tags
`profile` adds the share of sampled non-null values that match each value kind (Spark `rlike`, one aggregation per table):
email, phone (needs +, (, space, or dash; never an IPv4 address), IP, UUID, URL, JSON, user agent, long hash/token, text timestamp.
`core.classify_column` combines: name sets (log, audit, secret, personal, free text), these ratios (>= 0.5, or >= 0.2 with a log name),
the table's number of log-like names, and Unity Catalog tags/masks. Values of personal, secret, log, and free-text columns are
replaced by `<redacted>` BEFORE the profile is written (`core.redact_values`). Shapes (`aaaa@aaa.aaa`) and ratios stay.

## 3. Decision thresholds (defaults, in information.yaml)
- FK: containment >= 0.98 (raw or normalised). Partial link: >= 0.80 -> card. Below: no link.
- "Matches only after normalisation": a key rule is needed (CP3b).
- Reference table: <= 1000 rows, <= 4 columns, code-like key or description column.
- Lineage level 0 = root tables (referenced, referring to nothing). Level n depends on lower levels.

## 4. Composite keys (SAP-style header / line / schedule line)
- Keys up to `max_key_size` (4) columns. Column names that also exist in other tables of the source (MANDT, EBELN) are tried first: shared names are join-key parts far more often than attributes.
- n-ary links are built from plausible unary parts (the MIND/BINDER idea): for a composite key k1..kn, each component gets its best-named compatible columns in the other table; combinations are tested as distinct tuples (a tuple with a NULL part references nothing).
- Transitive links are dropped: schedule(MANDT+EBELN) -> header is implied by schedule(MANDT+EBELN+EBELP) -> line -> header.
- Roles by structure: a key = parent FK + one more column is a line table; a table whose key is referenced by a child with many rows per key and that has a date is a header.

## 5. Known limits
- Lineage system tables keep about one year and cover only Unity Catalog workloads; a feed written by an external tool shows as a path or not at all.
- Declared constraints are informational in Databricks (not enforced); discovery verifies them like any candidate.
- Value-kind regexes are heuristics: a person confirms every personal-data and log column at CP2 (card or decision sheet).
- Functional dependencies (non-key) are not searched; denormalised attributes show up as warnings on cards.
- Name-based ontology mapping needs the `abbreviations` list in business.yaml. Add source abbreviations as you find them.
