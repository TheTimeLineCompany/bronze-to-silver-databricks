# Triage guidance - examples

## Good read plans (short, precise, with a reason)
```yaml
- file_id: IF-0004
  path: 00_inbox/02_Profiling/CNTRK_profiling_v3_FINAL.xlsx
  doc_type: profiling_workbook
  relevance: core
  status: confirmed
  reason: latest profiling workbook (v3 FINAL); v1 is ignored
  read_plan:
    sheets: [LEGS]                 # p2-1-doc-profiles reads only these sheets
    why: column meaning, keys, client confidence per column

- file_id: IF-0001
  path: 00_inbox/01_Overview/CNTRK_solution_overview.docx
  doc_type: system_overview
  relevance: core
  status: confirmed
  reason: grain and table list
  read_plan:
    sections: ["2 Scope", "3 Data model"]
    why: grain, tables, legs
```

## Bad read plans
- `read_plan: all` - not allowed. Name the parts.
- A core file with no `why`.
- Two versions of the same document both `core`.

## How to decide fast
1. Does the file talk about this source's business objects (see `registry/sources.yaml`)? No -> `ignore` or `background`.
2. Is it the latest version? No -> `ignore`.
3. Does it define structure (columns, keys) or rules (formulas, codes)? Yes -> `core`.
4. Does it only confirm or illustrate? -> `supporting`.
5. Is it a discussion (email, minutes)? -> `background`.
