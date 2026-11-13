---
name: p2-1-triage
description: Step P2.1. Run the nb_p2_documents notebook (inventory, triage, extracts) for one application, review the triage, adjust relevance and reading plans, and record document claims as evidence. Use after P1, and again when new files arrive in the inbox or uploads/.
---

# P2.1 Documents

## Run
Run `notebooks/nb_p2_documents` with `project_root`, `app`, `run_by = genie`. Read its `Result:` cells.
No documents in the inbox → note it, continue with `@p2-2-compare` (the gaps become assumptions).

## Inputs
`documents/inventory.vNNN.json`, `documents/triage.vNNN.yaml`, `documents/extracts/IF-nnnn.vNNN.md` (already redacted).

## Steps
1. Read the triage. Check: copies and old versions are `ignore`; emails and minutes are `background`; core files ≤ 15.
2. Change a relevance or reading plan only with a reason; save the triage as a new version (`python -m b2s save <app> documents/triage <file> --reason "..." --via genie`).
3. List files the notebook could not read (images, image-only PDFs). Tell the worker; they may need an extractor (`@fw-integrate`).
4. Read only the reading plan of core and supporting files (the extracts). Do not open the inbox.
5. Record what the documents say about **what the application does, its workflows and its dependencies** as evidence:
   `python -m b2s item new <app> evidence --data '{"statement": "...", "confidence": "medium", "origin": {"type": "document", "ref": "IF-0003", "location": "section 2"}, "root_source": "IF-0003", "authority_class": "client_truth|proposed|team"}' --via genie`
   One claim < 40 words. Mark `proposed` for documents that describe a proposal, not the running system.

Then continue with `@p2-2-compare`.
