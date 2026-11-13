# Changelog

## 1.4.0 (in progress, branch v1.4)
Keeps the V1.3 sequence (P0–P6, CP1–CP6) and upgrades what runs inside it. The repository is now one agent-run
framework; the 2.4.0 tools, sample sources and registry are replaced (they remain in the git history, commit db4fc1b).

- **Agent-run:** `@b2s-run` reads the status and runs every step, including the notebooks (`run_by` recorded in each event). First use integrates the client's own notebooks and templates (`@p0-setup` → `@fw-integrate`).
- **State as files:** versioned, write-once files (`<name>.vNNN.<ext>` + sidecar with input versions), one file per item, events, O_EXCL locks, leases, a write guard for tests. No tables needed.
- **Stale detection and rerun plan:** step fingerprints from input content, step version and settings.
- **Checkpoints in the chat:** `I, <name>, approve CP3 logical.v004.`; pre-filled templates with decisions; chain rule; CP3 required before P4; CP5 and CP6 automatic; handoff states self-approval.
- **P1:** baseline engine with redaction before write, key limits and removed-by-rule, near keys, copies, stable open-point ids, resume; client profiler as a notebook plug-in.
- **P2:** documents (duplicates, compare, unreadable, redacted extracts), comparison with the baseline, new **P2.2b application understanding** with dependencies, process and conceptual models; scope and privacy proposal with column meanings.
- **P3:** logical silver model drafted from the conceptual model and the baseline keys.
- **Models:** YAML → Mermaid → HTML viewer, checked to match; no overlapping boxes, WCAG contrast.
- **Glean:** conceptual rounds before column rounds; raw reply saved first; root source on every claim.
- **P4:** canonical STTM drafted from the approved model, validator, export plug-ins, mapping model.
- **P5, P6:** code generation, master build, QA and release ported from 2.4.0 onto the canonical STTM.

## 2.4.0 (2026-10-31) - first public release (V1.1 design)
- Interactive input loop, Unity Catalog metadata and lineage first, table and column scope, privacy handling, composite keys, survivorship, SCD2, checkpoint packs CP1–CP6, feedback and upstream issues.
