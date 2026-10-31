# Bronze-to-Silver Databricks

**An agent-assisted framework for moving many source systems from the bronze layer to a clean, modelled silver layer on Databricks.**
Medallion architecture, done as a repeatable process: automated data discovery and profiling on Unity Catalog, an ontology that keeps
30+ sources coherent, source-to-target mapping (STTM) as code, PySpark generation, QA, and human checkpoints with feedback loops.

[![pr-checks](../../actions/workflows/pr-checks.yml/badge.svg)](../../actions/workflows/pr-checks.yml)
![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Databricks](https://img.shields.io/badge/Databricks-Unity%20Catalog%20%7C%20Genie%20Code-orange)

> Keywords: Databricks, Unity Catalog, lakehouse, medallion architecture (bronze, silver, gold), Delta Lake, PySpark, data modelling,
> data discovery, data profiling, foreign key discovery, data lineage, source-to-target mapping (STTM), ER model, ontology,
> master data management, survivorship, SCD Type 2, data quality, PII detection, data governance, AI agents, agentic data engineering,
> Databricks Genie Code, LLM, supply chain.

---

## Why this exists

Bronze-to-silver work across many source systems fails in the same places every time:

- **The input dump is huge.** Hundreds of documents, profiling workbooks, schema exports, and emails per source. People and agents drown in it.
- **Nobody knows what the bronze tables really are.** Which table is a master, a transaction line, an aggregate, a backup copy, or an application log? What is the grain? Which columns join?
- **Thirty sources use thirty vocabularies.** "Vendor", "supplier", and "provider" end up as three silver tables.
- **Logs and personal data leak into silver.** Login times, IP addresses, session ids, emails, and phone numbers sit in business tables.
- **The mapping and the code drift apart.** The STTM lives in a spreadsheet, the code is hand-written, and QA is a checklist nobody runs.
- **Reviews are approve or reject.** There is no structured way to say "redo this with that file" and have the right steps rerun.

This framework turns that into a process with code where code is reliable, agents where judgement is needed, and people at checkpoints.

## What you get

| Capability | How |
|---|---|
| **Automated bronze discovery** | Unity Catalog metadata first (`information_schema`, tags, masks, declared PK/FK, `SHOW STATISTICS`, `DESCRIBE HISTORY`), lineage system tables (`system.access.table_lineage`, `column_lineage`), then sampled profiling, minimal unique keys (composite, SAP-style), foreign-key discovery by value containment, table roles, grain, and lineage order. Never `SELECT *` on a whole table. |
| **Scope and privacy by name AND content** | Each column is classified from its name, the share of values that look like email, phone, IP, user agent, URL, JSON, UUID, or token, and its Unity Catalog tags. Application logs, audit columns, and secrets stay out of silver; personal data needs explicit handling (keep tagged, mask, or hash). Sensitive values are removed before anything is written to disk. |
| **Three-layer ontology** | Business (objects, synonyms, relationships, rules), data (classes, load patterns, keys), information (documents, evidence, confidence, phases). Every silver column traces back to evidence and its origin. |
| **STTM as code** | `sttm.yaml` with a JSON Schema and a validator: keys, FKs (incl. composite), cardinality, history rules, provenance, scope, privacy. Exports to Excel and Mermaid ER. |
| **PySpark generation** | Safe-to-rerun notebook generator, shared key normalisation, SCD2 with late-arriving data, unknown members, survivorship for shared masters, and Unity Catalog publishing (comments, tags, masks, informational PK/FK). |
| **QA as code** | The client's QA checklist mapped to `lib/qa_checks.py`; a checkpoint cannot pass with a missing check. |
| **Human checkpoints with packs** | CP1 to CP6, each with one HTML page, an Excel workbook, JSON, and a text summary. Packs know their inputs by hash, so a stale pack blocks approval. |
| **Interactive input loop** | Type an instruction, give feedback, or upload a file at any point. Each input is checked against all three ontology layers, an agent asks only the questions that matter, and the input is routed to the steps that must use it. |
| **Feedback and upstream issues** | Feedback items (comment, paths, code, data slice, attachments, answer) drive targeted reruns. Later phases raise issues back to earlier phases instead of working around them. |
| **Agent-ready** | Built for Databricks Genie Code skills (`SKILL.md`) and `AGENTS.md`; a card runner can answer discovery cards in parallel on a model serving endpoint. Works with any agent that can read files and run Python. |

## The process

```
P0 Setup ─ P1 Intake ─(CP1)─ P2 Discovery & evidence ─(CP2)─ P3 Central model ─(CP3, CP3b)─
           P4 Mapping (STTM) ─(CP4, CP4b)─ H1 ─ P5 Build & QA ─(CP5)─ P6 Handoff ─(CP6)─ H2
```

| Phase | Agents do | Code does | People do |
|---|---|---|---|
| P1 Intake | triage the dump, write a short source brief with evidence | inventory, duplicates, versions, budgets | confirm the files to read (CP1) |
| P2 Discovery | answer one decision card per chat | metadata, lineage, profiling, keys, links, roles, scope, privacy | check roles, scope, personal data (CP2) |
| P3 Central model | propose change requests | ontology coherence checks | approve objects and key rules (CP3, CP3b) |
| P4 Mapping | write `sttm.yaml` | validate, export Excel + ER | approve mapping and business logic (CP4, CP4b) |
| P5 Build | complete generated notebooks | generate, run QA | approve code and QA (CP5) |
| P6 Handoff | write the readiness report | check completeness | approve the handoff (CP6) |

A picture of the whole flow: [`docs/process_map.html`](docs/process_map.html). The full explanation: [`docs/FRAMEWORK_GUIDE.md`](docs/FRAMEWORK_GUIDE.md).
Step-by-step set up and daily use, skill by skill: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## Quick start

### Try it locally (no Databricks needed)
```bash
git clone https://github.com/TheTimeLineCompany/bronze-to-silver-databricks.git
cd bronze-to-silver-databricks
pip install -r requirements-ci.txt
python -m pytest -q tests/                      # ~110 tests; Spark tests skip without pyspark
python tools/x_navigator.py S07_container_moves  # where the example source is, and the next step
```
With `pyspark` installed, `RUN_SPARK=1 python -m pytest -q tests/` also runs bronze discovery end to end on a fake
container-tracking schema (with an application log table, a contact table with personal data, and SAP-style composite keys).

### Use it on Databricks
1. Add this repository as a **Git folder** in your workspace.
2. In Genie Code: **Settings → Add folder → `<Git folder>/skills`**. Genie Code reads `AGENTS.md` automatically.
3. Open the notebook **`00_start_here`**, set **action** to `setup-check`, and click **Run all**. It must print `SETUP OK`.
4. Add a source with action `new-source` (source id + bronze schema). Put the documents in `sources/<id>/00_inbox/` as they are.
5. Set **action** to `next` and follow the page. It tells you when a step is code (it runs it), an agent (it shows what to type in Genie Code), or a person (what to review).
6. Give input any time: `give-instruction`, `give-feedback`, or upload files to `sources/<id>/uploads/` and run `register-uploads`.

Unity Catalog grants: read-only on bronze for phases P1 to P4; write only to a dev silver schema in P5.

## Adapt it to your organisation
| File | Put in your own |
|---|---|
| `registry/ontology/business.yaml` | business objects, synonyms, abbreviations, relationships, business rules |
| `registry/entities.yaml`, `registry/key_normalisation.yaml` | shared master entities, key formats, survivorship |
| `standards/` | naming, coding, QA checklist, privacy tags and mask function |
| `registry/ontology/information.yaml` | document types, confidence rules, discovery budgets |
| `.github/CODEOWNERS.example` | copy to `.github/CODEOWNERS` with your approver teams |

The example sources (`S01_buyer_master`, `S07_container_moves`), documents, bronze data, and entities are **fictional** and use a supply-chain domain. Replace them with yours.

## Repository map
| Path | What |
|---|---|
| `00_start_here.py` | entry notebook: status, next step, run code steps, instructions, feedback, uploads, clarify |
| `AGENTS.md` | always-on rules for agents |
| `skills/` | 17 agent skills, one per step (`SKILL.md` + templates + references) |
| `sources/<id>/` | one folder per source: `00_inbox` → `01_intake` → `02_evidence` → `04_mapping` → `05_build` → `06_handoff` |
| `registry/` | ontology, entities, key rules, source status, questions, decisions, feedback board |
| `tools/` | discovery (`p2_2_discover.py`, `discovery/`), validators, generators, checkpoint packs, feedback, navigator, input check, clarify |
| `lib/` | PySpark library: keys, load patterns (SCD2), QA checks, survivorship, Unity Catalog publish |
| `schemas/`, `standards/` | STTM JSON Schema; naming, coding, QA, privacy |
| `tests/` | validator, discovery, and Spark tests, plus a fake bronze fixture |
| `.github/` | PR check workflow, PR template, CODEOWNERS example |

## Design principles
- **Code for guarantees, agents for judgement, people for approval.** Every gate is a script, not a prompt.
- **Never read everything.** A funnel for documents and budgets for bronze profiling keep cost and context small.
- **Evidence for every mapping.** Bronze wins for structure, documents win for meaning, a client answer wins for both.
- **Ask, do not guess.** Unknown names, conflicts, and new concepts become short questions; "I don't know" becomes a client question.
- **Personal data never reaches a file.** Only ratios and shapes are stored for sensitive columns.

## Method and references
Data profiling: Abedjan, Golab, Naumann, *Profiling relational data: a survey* (VLDB Journal, 2015) and *Data Profiling* (2018);
key discovery (HCA/DUCC), inclusion dependencies (SPIDER, MIND/BINDER), foreign-key ranking (Rostin et al., 2009; Zhang et al., 2010).
Grain and table roles: Kimball & Ross, *The Data Warehouse Toolkit*, 3rd ed.
Databricks documentation: `information_schema`, lineage system tables, `SHOW STATISTICS`, `DESCRIBE HISTORY`, table constraints,
data classification, column masks, Genie Code skills. Details: [`skills/p2-2-bronze-discovery/references/methods.md`](skills/p2-2-bronze-discovery/references/methods.md).

## Status and limits
- Version 2.4. Tested with local Spark 3.5 and pure-Python validators. The Unity Catalog metadata and lineage code degrades safely when a view or privilege is missing, and needs a real workspace for a full run.
- Column classification and input analysis are rule-based heuristics. They narrow the questions; a person confirms scope and personal data at CP2.
- Genie Code has no documented hooks or sub-agents; enforcement uses scripts, PR checks, CODEOWNERS, and Unity Catalog grants.

## Contributing
Issues and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License
Apache License 2.0. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).

*This is an independent open-source project. It is not affiliated with, endorsed by, or sponsored by Databricks, Inc.
"Databricks", "Unity Catalog", "Delta Lake", and "Genie" are trademarks of their owners.*
