"""Card runner: answer open discovery cards with one fresh LLM call per card (sub-agents), in parallel.

The cards (02_evidence/discovery/cards/T-xxx.md) are the contract. Any runtime can answer them:
  - a person or Genie Code, one card per chat (`@p2-2-bronze-discovery card <file>`);
  - this runner, against a Databricks Model Serving endpoint (OpenAI-compatible API);
  - a Databricks multi-agent app / Agent Bricks supervisor that wraps `answer_card` as a tool.

Each call gets ONLY: the card, the source brief, and the skill rules. No shared memory between cards.
Answers are validated; an invalid answer is retried once, then left open for a person.

Usage (Databricks notebook):
    from discovery.card_runner import run, databricks_llm
    run("S07_container_moves", databricks_llm("databricks-claude-sonnet-4-5"), max_workers=4)
Then: python tools/p2_2_discover.py merge S07_container_moves
"""
from __future__ import annotations

import glob
import os
import re
from concurrent.futures import ThreadPoolExecutor

import yaml

ROLES = {"master", "reference", "transaction_header", "transaction_line", "event", "snapshot", "bridge", "aggregate", "technical", "staging"}
LOAD = {"yes", "no", "derive_instead"}

SYSTEM = """You answer ONE bronze discovery card for a bronze-to-silver data modelling project.
Rules:
- Decide only what the card asks. Use only the facts on the card and the source brief.
- Use a business object name from the card's allowed list, or NEW:<Name>, or none.
- A key or link is proven only by the numbers on the card. Do not invent columns or values.
- If the problem belongs to an earlier phase, write it in raise_upstream. Do not work around it.
- Application or operational tables (login, session, audit, error, job, config logs) are role technical, load_to_silver no.
- reason: max 40 words, simple technical English.
Reply with ONE yaml code block in the card's answer format and nothing else."""


def databricks_llm(endpoint: str, temperature: float = 0.0):
    """LLM callable for a Databricks serving endpoint (OpenAI-compatible). Needs the `openai` package."""
    from openai import OpenAI
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:  # inside a notebook: use the notebook context
        ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()  # noqa: F821
        host, token = "https://" + ctx.browserHostName().get(), ctx.apiToken().get()
    client = OpenAI(api_key=token, base_url=f"{host.rstrip('/')}/serving-endpoints")

    def call(system: str, user: str) -> str:
        r = client.chat.completions.create(model=endpoint, temperature=temperature,
                                           messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    return call


def parse(text: str) -> dict:
    m = re.search(r"```(?:yaml)?\s*(.*?)```", text, re.S)
    return yaml.safe_load(m.group(1) if m else text) or {}


def validate(ans: dict, card_id: str, allowed_objects: set) -> list:
    errs = []
    if isinstance(ans.get("load_to_silver"), bool):           # YAML reads yes/no as true/false
        ans["load_to_silver"] = "yes" if ans["load_to_silver"] else "no"
    if ans.get("card") != card_id:
        errs.append(f"card must be {card_id}")
    if ans.get("role") not in ROLES:
        errs.append(f"role must be one of {sorted(ROLES)}")
    bo = str(ans.get("business_object") or "none")
    if bo != "none" and not bo.startswith("NEW:") and bo not in allowed_objects:
        errs.append(f"business_object '{bo}' is not in business.yaml (use NEW:<Name> or none)")
    if str(ans.get("load_to_silver")) not in LOAD:
        errs.append(f"load_to_silver must be one of {sorted(LOAD)}")
    if not ans.get("reason") or len(str(ans["reason"]).split()) > 45:
        errs.append("reason is required, max 40 words")
    if not isinstance(ans.get("grain_key") or [], list):
        errs.append("grain_key must be a list")
    return errs


def answer_card(card_path: str, brief: str, llm, allowed_objects: set) -> dict:
    """One sub-agent: fresh context, one card. Returns {card, ok, errors, path}."""
    cid = os.path.basename(card_path)[:-3]
    card = open(card_path, encoding="utf-8").read()
    user = f"{card}\n\n## Source brief\n{brief}"
    errs = []
    for attempt in range(2):
        text = llm(SYSTEM, user if attempt == 0 else user + "\n\nYour last answer was invalid: " + "; ".join(errs) + ". Answer again.")
        try:
            ans = parse(text)
        except yaml.YAMLError as e:
            errs = [f"not valid yaml: {e}"]
            continue
        errs = validate(ans, cid, allowed_objects)
        if not errs:
            ans["answered_by"] = "card_runner"
            out = card_path[:-3] + ".result.yaml"
            with open(out, "w", encoding="utf-8") as f:
                yaml.safe_dump(ans, f, sort_keys=False, allow_unicode=True)
            return {"card": cid, "ok": True, "errors": [], "path": out}
    return {"card": cid, "ok": False, "errors": errs, "path": None}


def run(source_id: str, llm, root: str | None = None, max_workers: int = 4, only: list | None = None) -> list:
    root = root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(root, "sources", source_id, "02_evidence", "discovery", "cards")
    bp = os.path.join(root, "sources", source_id, "01_intake", "source_brief.md")
    brief = open(bp, encoding="utf-8").read() if os.path.exists(bp) else "(no brief)"
    with open(os.path.join(root, "registry", "ontology", "business.yaml"), encoding="utf-8") as f:
        objs = set(yaml.safe_load(f)["business_objects"])
    cards = [c for c in sorted(glob.glob(os.path.join(d, "T-*.md")))
             if not os.path.exists(c[:-3] + ".result.yaml") and (not only or os.path.basename(c)[:-3] in only)]
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(lambda c: answer_card(c, brief, llm, objs), cards))
