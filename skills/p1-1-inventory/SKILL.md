---
name: p1-1-inventory
description: Step P1.1. List every file in a source dump (sources/<id>/00_inbox) with a script, find duplicates and old versions, and suggest a document type for each file - without reading the files. Use first for a new source, and again when files are added to the inbox.
---

# P1.1 Inventory (phase P1, checkpoint CP1_source_brief)

## Goal
Make the dump small and known BEFORE any reading. The script does the work. You do not open inbox files in this step.

## Before you start
1. `python tools/x_feedback.py list <id> --open` - apply open feedback for `CP1_source_brief` first (for example `include_paths`, `ignore_paths`).

## Steps
1. Run `python tools/p1_1_inventory.py <id>`.
   - New files added later: run it with `--refresh-triage`. Existing triage lines are kept.
2. Read ONLY `sources/<id>/01_intake/manifest.md`. Do not read `manifest.csv` line by line.
3. Check the summary:
   - number of files, exact duplicates, version groups, suggested types;
   - files with type `unrelated` or `unknown` - note them for triage.
4. Log the run: `python tools/x_feedback.py log <id> p1-1-inventory --note "<n> files, <d> duplicates"`.

## Outputs
- `01_intake/manifest.csv` (all files, IF-0001 ...), `01_intake/manifest.md` (summary).
- `01_intake/triage.yaml` draft (only when it does not exist).

## Rules
- Never open a file from `00_inbox` in this step.
- Never delete or move inbox files. Use `ignore` in triage instead.
- Do not edit `manifest.csv` by hand. Run the script again.

## Done when
`manifest.md` exists and the next step (`@p1-2-triage`) can start.
