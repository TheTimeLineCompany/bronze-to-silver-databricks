# 05_build - P5 Build (checkpoint CP5_code_qa)

Purpose: PySpark code and QA proof. This is the code that goes to Git and to the deployment team.

| Path | Written by | Read by |
|---|---|---|
| `nb_slv_<id>_<table>.py` | `tools/p5_1_gen_notebook.py` + p5-1 (TODO cells) | Job, review |
| `job_slv_<id>.json` | p5-1 | deployment |
| `qa_results/<table>.json`, `qa_results/summary.json` | notebooks (`lib/qa_checks.py`) | checkpoint check, CP5 pack |
| `reviews/code_review.md` | p5-3 (new chat) | checkpoint check |
| `checkpoint/CP5_code_qa.*` | `tools/x_checkpoint_pack.py <id> CP5_code_qa` | reviewer (the QA document) |
| `feedback/CP5_code_qa/` | reviewers, agents | p5-1, p5-2 at rerun |

QA rules: `standards/qa_checklist.md`. QA code: `lib/qa_checks.py`.
