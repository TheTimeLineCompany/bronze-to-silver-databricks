# Changelog

## 2.4.0 (2026-10-31) - first public release
- Interactive input loop: typed instructions, feedback, and uploaded files are checked against the business, data, and information ontology; `@x-clarify` asks only pertinent questions; answers are routed to the steps that use them.
- Bronze discovery uses Unity Catalog metadata and lineage first: comments, tags, masks, declared keys, statistics, history, table and column lineage; related tables outside the schema; documents-vs-bronze gaps; overlap between sources.
- Table and column scope: application logs, audit columns, secrets, and personal data detected by name, content, and tags. Sensitive values are removed before files are written.
- STTM validator checks scope overrides and privacy handling; generated notebooks publish comments, tags, masks, and informational PK/FK to Unity Catalog.
- Composite keys and foreign keys (SAP-style), survivorship for shared masters, unknown members, SCD2 with late-arriving data.
- `00_start_here` notebook and navigator; checkpoint packs (HTML, Excel, JSON, text) at CP1 to CP6; feedback and upstream issues with targeted reruns.
