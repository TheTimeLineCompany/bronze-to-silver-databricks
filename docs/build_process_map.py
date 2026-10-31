"""Regenerate docs/process_map.html.  Usage: python docs/build_process_map.py . /tmp/process_map_body.html
(The second file is a body-only copy for publishing as a web artifact.)"""
"""Builds docs/process_map.html (standalone) and an artifact body version from one data structure."""
import html, sys, os

KIT = sys.argv[1]
OUT_ART = sys.argv[2]
e = html.escape

PHASES = [
 dict(id="P0", name="Setup", scope="once", cp=[], steps=[
   dict(n="P0", skill="README.md", agent=["Nothing yet. Genie Code reads AGENTS.md automatically once the Git folder exists."],
        code=["pytest -q tests/", "x_ontology_check.py", "PR check workflow + CODEOWNERS"],
        human=["Create the Git folder; register skills/ in Genie Code (Settings → Add folder)",
               "Agree the business ontology with the client", "Copy standards/, fill sources.yaml, set UC grants"],
        out="Repo ready, ontology agreed")]),
 dict(id="P1", name="Intake and focus", scope="per source", cp=["CP1_source_brief"], steps=[
   dict(n="P1.1", skill="p1-1-inventory", agent=["Reads ONLY manifest.md"],
        code=["p1_1_inventory.py: IF-ids, hashes, duplicates, version groups, suggested doc type"],
        human=["Drops the dump into 00_inbox as it is"], out="01_intake/manifest.md"),
   dict(n="P1.2", skill="p1-2-triage", agent=["Sets doc type + relevance per file", "Writes a read plan for core / supporting files", "Keeps one version per group"],
        code=["p1_2_check_context.py --only triage: all files classified, ≤15 core, read plans present"],
        human=["Can add include_paths / ignore_paths feedback", "Only a person sets a budget_override"], out="01_intake/triage.yaml"),
   dict(n="P1.3", skill="p1-3-source-brief", agent=["Reads only read-plan parts of core files", "Writes short claims E-xxxx with origin + confidence", "Maps source words to business objects", "Raises questions"],
        code=["p1_2_check_context.py: brief ≤1800 words, cites existing E-ids; claims ≤40 words"],
        human=["Reviews the brief in the PR"], out="source_brief.md + evidence_register.csv")]),
 dict(id="P2", name="Discovery and evidence", scope="per source", cp=["CP2_evidence"], steps=[
   dict(n="P2.1", skill="p2-1-doc-profiles", agent=["Reads only the summary; filters the CSV"],
        code=["p2_1_extract_doc_profiles.py: client workbooks → one table, confidence normalised to high/medium/low/unknown"],
        human=["Adds header synonyms when a workbook is not extracted"], out="02_evidence/profiling/doc_profiles.csv"),
   dict(n="P2.2", skill="p2-2-bronze-discovery", agent=["Orchestrates the job; reads only summary.md", "Answers one card per chat (or the card runner does, one LLM call per card)", "Raises upstream issues (new object, grain conflict)"],
        code=["Unity Catalog metadata + lineage first (no data read)", "Parallel job: profile on a sample, exact key checks, value containment between columns", "Roles, grain, lineage, ontology map; table and column scope (logs, personal data)", "Merge answers → evidence lines"],
        human=["Checks roles, business objects, scope, and personal data in the CP2 page", "Accepts or rejects upstream issues"], out="02_evidence/discovery/"),
   dict(n="P2.3", skill="p2-3-evidence-reconcile", agent=["Sets status: corroborated, confirmed_by_bronze, contradicted, superseded", "Bronze wins structure; documents win meaning", "Updates the brief"],
        code=["p1_2_check_context.py: register valid; corroborated needs a reference", "Gate needs ≥1 bronze result"],
        human=["Answers questions (answer feedback)", "Approves CP2 in the PR"], out="evidence_register.csv (reconciled)")]),
 dict(id="P3", name="Central model", scope="global", cp=["CP3_central_model", "CP3b_key_rules"], steps=[
   dict(n="P3.1", skill="p3-1-entity-model", agent=["Finds gaps: new object, synonym, relationship, key format", "Writes a change request CR-nnn; never edits silently"],
        code=["x_ontology_check.py: domains, synonyms, relationships, entities, sources coherent"],
        human=["Data architect approves CP3 (objects, entities) and CP3b (key rules, survivorship)"], out="ontology + entities.yaml + key rules")]),
 dict(id="P4", name="Mapping", scope="per source", cp=["CP4_sttm", "CP4b_business_logic"], handover="H1", steps=[
   dict(n="P4.1", skill="p4-1-sttm-author", agent=["Writes sttm.yaml: business object, data class, grain, keys, joins, FKs, transforms, BR ids, evidence ids", "Never goes back to 00_inbox"],
        code=["schema: sttm.schema.json"], human=["Gives comment / code feedback on columns"], out="04_mapping/sttm.yaml"),
   dict(n="P4.2", skill="p4-2-sttm-validate", agent=["Explains each error and fixes it"],
        code=["p4_2_validate_sttm.py: structure, naming, registry, ontology chain, FK ↔ relationship, confidence rules"],
        human=["—"], out="validator PASS"),
   dict(n="P4.3", skill="p4-3-sttm-review", agent=["NEW chat: checklist review, spot-checks 5 evidence ids"],
        code=["Gate reads ‘Result: PASS’"], human=["Phase 1 lead approves CP4"], out="04_mapping/reviews/sttm_review.md"),
   dict(n="P4.4", skill="p4-4-sttm-export", agent=["Sends the Excel to the SME when business logic exists"],
        code=["p4_4_export_sttm.py: Excel + Mermaid ER"], human=["Client SME signs off formulas (CP4b)"], out="exports/ + business_logic_signoff.md")]),
 dict(id="P5", name="Build", scope="per source", cp=["CP5_code_qa"], steps=[
   dict(n="P5.1", skill="p5-1-pyspark-codegen", agent=["Completes only TODO(genie) cells: dedup, joins, lookups, derived", "Writes the Job JSON"],
        code=["p5_1_gen_notebook.py: deterministic skeleton; lib/keys, lib/load_patterns"], human=["Gives code feedback (snippets)"], out="05_build/nb_*.py, job"),
   dict(n="P5.2", skill="p5-2-qa-runner", agent=["Explains each failure: code bug, STTM gap, or data problem"],
        code=["lib/qa_checks.py: QA-01…07 → qa_results/summary.json"], human=["Gives data feedback: rows to check"], out="qa_results/summary.json"),
   dict(n="P5.3", skill="p5-3-code-review", agent=["NEW chat: code vs STTM, standards, QA"],
        code=["Gate: QA all pass + ‘Result: PASS’"], human=["Phase 2 lead approves CP5"], out="05_build/reviews/code_review.md")]),
 dict(id="P6", name="Handoff", scope="per source", cp=["CP6_handoff"], handover="H2", steps=[
   dict(n="P6.1", skill="p6-1-handoff-package", agent=["Writes readiness.md: deliverables, run order, limits, feedback history"],
        code=["x_validate_gate.py: exports + readiness exist, no blocking questions"], human=["Deployment lead approves CP6"], out="06_handoff/readiness.md")]),
]

CPS = {
 "CP1_source_brief": dict(who="Phase 1 lead", approves="Triage and brief are right; the agent reads the right files", code="All files triaged, ≤15 core, read plans, brief cites existing E-ids", fb="include_paths, ignore_paths, comment, attachments", now="p1-2, p1-3", reset="CP1 → CP6"),
 "CP2_evidence": dict(who="Phase 1 lead", approves="Evidence is enough; conflicts handled; questions raised", code="Register well formed; discovery done; all cards answered; no upstream issue open", fb="data, answer, comment, include_paths", now="p2-3 (rerun_from p2-2 for data)", reset="CP2 → CP6"),
 "CP3_central_model": dict(who="Data architect", approves="Business objects, relationships, shared entities", code="All entities approved; ontology coherent", fb="comment, attachments", now="p3-1", reset="CP3, CP3b + every source CP4 → CP6"),
 "CP3b_key_rules": dict(who="Data architect", approves="Key formats and which source wins", code="CP3 approved first", fb="comment, data, code", now="p3-1", reset="CP3, CP3b + every source CP4 → CP6"),
 "CP4_sttm": dict(who="Phase 1 lead", approves="The mapping", code="Validator PASS, STTM approved, review PASS, CP3/CP3b approved", fb="comment, code, data", now="p4-1 → p4-4", reset="CP4 → CP6"),
 "CP4b_business_logic": dict(who="Client SME", approves="Formulas of business-logic columns", code="Sign-off file PASS (required when business_logic columns exist)", fb="comment, answer, code", now="p4-1 → p4-4", reset="CP4 → CP6"),
 "CP5_code_qa": dict(who="Phase 2 lead", approves="Code matches STTM and standards", code="QA summary all pass; code review PASS", fb="code, data, comment", now="p5-1 → p5-3", reset="CP5, CP6"),
 "CP6_handoff": dict(who="Deployment lead", approves="Package is complete and runnable", code="Exports + readiness exist; no blocking question", fb="comment, attachments", now="p6-1", reset="CP6"),
}
HANDOVERS = {
 "H1": ("Phase 1 → Phase 2", "after CP4 + CP4b", ["04_mapping/ (approved sttm.yaml, exports/, reviews/, checkpoint/)", "02_evidence/evidence_register.csv"]),
 "H2": ("Phase 2 → Deployment", "after CP6", ["05_build/ (notebooks, job, qa_results/, checkpoint/)", "06_handoff/readiness.md", "04_mapping/exports/"]),
}

FOLDER = {"CP1_source_brief": "01_intake", "CP2_evidence": "02_evidence", "CP3_central_model": "registry", "CP3b_key_rules": "registry",
          "CP4_sttm": "04_mapping", "CP4b_business_logic": "04_mapping", "CP5_code_qa": "05_build", "CP6_handoff": "06_handoff"}


def li(items):
    return "".join(f"<li>{e(x)}</li>" for x in items)

def short(cp):
    return cp.split("_")[0]

# ---------- overview rail
rail = []
for p in PHASES:
    cps = "".join(f'<a class="cp-chip" href="#{p["id"]}">{short(c)}</a>' for c in p["cp"])
    ho = f'<span class="ho-chip">{p["handover"]}</span>' if p.get("handover") else ""
    rail.append(f'<li class="rail-item"><a class="rail-link" href="#{p["id"]}"><span class="rail-id">{p["id"]}</span>'
                f'<span class="rail-name">{e(p["name"])}</span><span class="rail-scope">{e(p["scope"])}</span></a>'
                f'<div class="rail-marks">{cps}{ho}</div></li>')
rail_html = '<ol class="rail">' + "".join(rail) + "</ol>"

# ---------- phase sections
secs = []
for p in PHASES:
    rows = []
    for s in p["steps"]:
        rows.append(f'''<div class="step">
  <div class="step-head"><span class="step-n">{e(s["n"])}</span><code class="skill">{"@" + e(s["skill"]) if not s["skill"].endswith(".md") else e(s["skill"])}</code><span class="step-out">→ {e(s["out"])}</span></div>
  <div class="lanes">
    <div class="lane lane-agent" data-lane="agent"><h4>Agent</h4><ul>{li(s["agent"])}</ul></div>
    <div class="lane lane-code" data-lane="code"><h4>Code</h4><ul>{li(s["code"])}</ul></div>
    <div class="lane lane-human" data-lane="human"><h4>Human</h4><ul>{li(s["human"])}</ul></div>
  </div>
</div>''')
    gates = []
    for c in p["cp"]:
        d = CPS[c]
        gates.append(f'''<div class="gate" data-lane="human">
  <div class="gate-head"><span class="gate-id">{short(c)}</span><code>{e(c)}</code><span class="gate-who">{e(d["who"])}</span></div>
  <dl class="gate-grid">
    <dt>Person approves</dt><dd>{e(d["approves"])}</dd>
    <dt>Code checks first</dt><dd>{e(d["code"])} · no open feedback · approver, date, PR filled</dd>
    <dt>Typical feedback</dt><dd>{e(d["fb"])}</dd>
    <dt>Rerun on feedback</dt><dd>now: <code>{e(d["now"])}</code> · back to pending: {e(d["reset"])}</dd>
    <dt>Checkpoint pack</dt><dd><code>{e(FOLDER[c])}/checkpoint/{e(c)}</code> .html · .xlsx · .json · .md</dd>
  </dl>
</div>''')
    ho = ""
    if p.get("handover"):
        h = HANDOVERS[p["handover"]]
        ho = f'''<div class="handover"><span class="ho-id">{p["handover"]}</span><div><strong>{e(h[0])}</strong> <span class="muted">{e(h[1])}</span><ul class="pkg">{li(h[2])}</ul></div></div>'''
    secs.append(f'''<section class="phase" id="{p["id"]}">
  <header class="phase-head"><span class="phase-id">{p["id"]}</span><h3>{e(p["name"])}</h3><span class="scope">{e(p["scope"])}</span></header>
  {"".join(rows)}
  {"".join(gates)}
  {ho}
</section>''')
phases_html = "".join(secs)

BODY = f'''<title>Silver Modelling Process Map</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Public+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
/* Layout: a shipping-manifest reading of the pipeline — phase rail on top, then one block per phase with three work lanes (agent / code / human) and checkpoint slips. */
:root {{
  --bg: #f4f6f7; --surface: #ffffff; --ink: #18232b; --muted: #5b6a74; --line: #d5dde2;
  --agent: #0f7c78; --agent-bg: #e3f3f1;
  --code: #3d4f9c; --code-bg: #e7eaf7;
  --human: #a3530b; --human-bg: #fbeedf;
  --gate: #8a1f2d; --gate-bg: #f8e6e8;
  --display: "Barlow Condensed", "Arial Narrow", "Helvetica Neue", sans-serif;
  --body: "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #12181c; --surface: #1a2227; --ink: #e3e9ec; --muted: #94a3ad; --line: #2c3840;
  --agent: #4fc3bc; --agent-bg: #143331; --code: #9aa9f0; --code-bg: #1e2540;
  --human: #f0a35a; --human-bg: #35261a; --gate: #f08a98; --gate-bg: #3a1d22; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #12181c; --surface: #1a2227; --ink: #e3e9ec; --muted: #94a3ad; --line: #2c3840;
  --agent: #4fc3bc; --agent-bg: #143331; --code: #9aa9f0; --code-bg: #1e2540;
  --human: #f0a35a; --human-bg: #35261a; --gate: #f08a98; --gate-bg: #3a1d22; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; line-height: 1.55; margin: 0; }}
.wrap {{ max-width: 1180px; margin: 0 auto; padding-block: 28px 64px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); display: grid; gap: 40px; }}
h1, h2, h3 {{ font-family: var(--display); text-wrap: balance; margin: 0; letter-spacing: .01em; }}
h1 {{ font-size: clamp(34px, 6vw, 54px); font-weight: 700; line-height: 1; }}
h2 {{ font-size: 30px; font-weight: 600; }}
h3 {{ font-size: 26px; font-weight: 600; }}
p {{ margin: 0; max-width: 68ch; }}
code {{ font-family: var(--mono); font-size: .86em; }}
.muted {{ color: var(--muted); }}
.eyebrow {{ font-family: var(--mono); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }}
.intro {{ display: grid; gap: 14px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.key {{ font-size: 13px; padding: 4px 10px; border-radius: 3px; border: 1px solid transparent; cursor: pointer; font-family: var(--body); font-weight: 600; }}
.key:focus-visible {{ outline: 2px solid var(--ink); outline-offset: 2px; }}
.key-agent {{ background: var(--agent-bg); color: var(--agent); }}
.key-code {{ background: var(--code-bg); color: var(--code); }}
.key-human {{ background: var(--human-bg); color: var(--human); }}
.key-all {{ background: var(--surface); color: var(--ink); border-color: var(--line); }}
.key[aria-pressed="true"] {{ border-color: currentColor; }}
.legend-note {{ font-size: 13px; color: var(--muted); }}
body.focus-agent [data-lane]:not([data-lane="agent"]),
body.focus-code [data-lane]:not([data-lane="code"]),
body.focus-human [data-lane]:not([data-lane="human"]) {{ opacity: .28; }}
/* rail */
.rail {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; }}
.rail-item {{ display: grid; gap: 6px; align-content: start; }}
.rail-link {{ display: grid; gap: 2px; text-decoration: none; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-top: 4px solid var(--ink); padding: 10px 10px 12px; }}
.rail-link:hover {{ border-color: var(--muted); }}
.rail-id {{ font-family: var(--display); font-size: 26px; font-weight: 700; line-height: 1; }}
.rail-name {{ font-weight: 600; font-size: 14px; }}
.rail-scope {{ font-family: var(--mono); font-size: 11px; color: var(--muted); }}
.rail-marks {{ display: flex; flex-wrap: wrap; gap: 4px; }}
.cp-chip, .ho-chip {{ font-family: var(--mono); font-size: 11px; padding: 2px 6px; text-decoration: none; }}
.cp-chip {{ background: var(--gate-bg); color: var(--gate); }}
.ho-chip {{ background: var(--ink); color: var(--bg); }}
@media (max-width: 860px) {{ .rail {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }} }}
@media (max-width: 480px) {{ .rail {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
/* phase */
.phase {{ display: grid; gap: 12px; scroll-margin-top: 12px; }}
.phase-head {{ display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; border-bottom: 2px solid var(--ink); padding-bottom: 6px; }}
.phase-id {{ font-family: var(--display); font-weight: 700; font-size: 40px; line-height: .9; }}
.scope {{ font-family: var(--mono); font-size: 12px; color: var(--muted); margin-left: auto; }}
.step {{ background: var(--surface); border: 1px solid var(--line); display: grid; }}
.step-head {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; padding: 10px 14px; border-bottom: 1px solid var(--line); }}
.step-n {{ font-family: var(--display); font-weight: 600; font-size: 20px; }}
.skill {{ color: var(--ink); font-weight: 500; }}
.step-out {{ font-family: var(--mono); font-size: 12px; color: var(--muted); min-width: 0; overflow-wrap: anywhere; }}
.lanes {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.lane {{ padding: 10px 14px 12px; min-width: 0; transition: opacity .15s; }}
.lane + .lane {{ border-left: 1px solid var(--line); }}
.lane h4 {{ margin: 0 0 4px; font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }}
.lane ul {{ margin: 0; padding-left: 18px; font-size: 14px; display: grid; gap: 2px; }}
.lane-agent h4 {{ color: var(--agent); }} .lane-agent {{ box-shadow: inset 0 3px 0 var(--agent); }}
.lane-code h4 {{ color: var(--code); }} .lane-code {{ box-shadow: inset 0 3px 0 var(--code); }}
.lane-human h4 {{ color: var(--human); }} .lane-human {{ box-shadow: inset 0 3px 0 var(--human); }}
@media (max-width: 760px) {{ .lanes {{ grid-template-columns: 1fr; }} .lane + .lane {{ border-left: 0; border-top: 1px solid var(--line); }} }}
/* gate slip */
.gate {{ background: var(--gate-bg); border: 1.5px dashed var(--gate); padding: 12px 14px; display: grid; gap: 8px; transition: opacity .15s; }}
.gate-head {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; }}
.gate-id {{ font-family: var(--display); font-weight: 700; font-size: 22px; color: var(--gate); }}
.gate-who {{ margin-left: auto; font-weight: 600; color: var(--human); font-size: 14px; }}
.gate-grid {{ display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 4px 14px; margin: 0; font-size: 14px; }}
.gate-grid dt {{ font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); padding-top: 3px; }}
.gate-grid dd {{ margin: 0; min-width: 0; }}
@media (max-width: 560px) {{ .gate-grid {{ grid-template-columns: 1fr; }} .gate-grid dd {{ margin-bottom: 6px; }} }}
.handover {{ display: flex; gap: 14px; align-items: flex-start; background: var(--ink); color: var(--bg); padding: 12px 16px; }}
.handover .muted {{ color: var(--bg); opacity: .7; }}
.ho-id {{ font-family: var(--display); font-weight: 700; font-size: 34px; line-height: 1; }}
.pkg {{ margin: 6px 0 0; padding-left: 18px; font-family: var(--mono); font-size: 12.5px; }}
/* generic panels */
.panel {{ display: grid; gap: 14px; }}
.two {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
@media (max-width: 760px) {{ .two {{ grid-template-columns: 1fr; }} }}
.box {{ background: var(--surface); border: 1px solid var(--line); padding: 14px 16px; min-width: 0; display: grid; gap: 8px; align-content: start; }}
.tbl-wrap {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--line); }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
th {{ font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 500; }}
tr:last-child td {{ border-bottom: 0; }}
/* lifecycle */
.life {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-family: var(--mono); font-size: 13px; }}
.st {{ padding: 4px 10px; border: 1px solid var(--line); background: var(--surface); }}
.st.block {{ border-color: var(--gate); color: var(--gate); }}
.st.ok {{ border-color: var(--agent); color: var(--agent); }}
.arrow {{ color: var(--muted); }}
pre.cli {{ margin: 0; background: var(--surface); border: 1px solid var(--line); padding: 12px 14px; overflow-x: auto; font-family: var(--mono); font-size: 12.5px; line-height: 1.5; }}
/* funnel */
.funnel {{ display: grid; gap: 4px; }}
.fn {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: baseline; padding: 8px 14px; background: var(--code-bg); margin-inline: calc(var(--i) * 3.2%); }}
.fn strong {{ font-weight: 600; }}
.fn .n {{ font-family: var(--mono); font-size: 12.5px; color: var(--code); font-variant-numeric: tabular-nums; text-align: right; }}
@media (max-width: 560px) {{ .fn {{ margin-inline: 0; grid-template-columns: 1fr; }} .fn .n {{ text-align: left; }} }}
/* ontology chain */
.chain {{ display: grid; gap: 0; counter-reset: c; }}
.link {{ display: grid; grid-template-columns: 170px minmax(0, 1fr) minmax(0, 1fr); gap: 12px; padding: 9px 14px; background: var(--surface); border: 1px solid var(--line); border-top: 0; font-size: 14px; }}
.link:first-child {{ border-top: 1px solid var(--line); }}
.link .lvl {{ font-weight: 600; }}
.link .src {{ font-family: var(--mono); font-size: 12.5px; color: var(--muted); overflow-wrap: anywhere; }}
.link .ex {{ font-family: var(--mono); font-size: 12.5px; overflow-wrap: anywhere; }}
.layer-b {{ box-shadow: inset 4px 0 0 var(--human); }}
.layer-d {{ box-shadow: inset 4px 0 0 var(--code); }}
.layer-i {{ box-shadow: inset 4px 0 0 var(--agent); }}
@media (max-width: 680px) {{ .link {{ grid-template-columns: 1fr; gap: 2px; }} }}
.layers {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
@media (max-width: 860px) {{ .layers {{ grid-template-columns: 1fr; }} }}
.layer h3 {{ font-size: 22px; }}
.layer ul {{ margin: 0; padding-left: 18px; font-size: 14px; display: grid; gap: 2px; }}
.layer.b {{ border-top: 4px solid var(--human); }} .layer.d {{ border-top: 4px solid var(--code); }} .layer.i {{ border-top: 4px solid var(--agent); }}
.conf {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }}
@media (max-width: 760px) {{ .conf {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.cf {{ padding: 10px 12px; border: 1px solid var(--line); background: var(--surface); font-size: 14px; display: grid; gap: 4px; align-content: start; }}
.cf b {{ font-family: var(--display); font-size: 20px; font-weight: 600; }}
.cf.h b {{ color: var(--agent); }} .cf.m b {{ color: var(--code); }} .cf.l b {{ color: var(--human); }} .cf.u b {{ color: var(--muted); }}
footer {{ font-size: 13px; color: var(--muted); border-top: 1px solid var(--line); padding-top: 12px; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; }} }}
</style>

<div class="wrap">
<header class="intro">
  <span class="eyebrow">Bronze → Silver · Databricks Genie Code · kit v2</span>
  <h1>Silver Modelling Process Map</h1>
  <p>Seven phases take one source system from a raw file dump to a deployable silver load. Each phase writes into its own numbered folder and ends with a checkpoint pack. Each step shows what the <b>agent</b> does, what <b>code</b> guarantees, and what a <b>human</b> decides. Red slips are checkpoints: a person approves them in a pull request, and can send feedback that reruns the steps before it.</p>
  <div class="legend" role="group" aria-label="Highlight one lane">
    <button class="key key-all" id="lane-all" data-focus="" aria-pressed="true">All lanes</button>
    <button class="key key-agent" id="lane-agent" data-focus="agent" aria-pressed="false">Agent</button>
    <button class="key key-code" id="lane-code" data-focus="code" aria-pressed="false">Code</button>
    <button class="key key-human" id="lane-human" data-focus="human" aria-pressed="false">Human</button>
    <span class="legend-note">Pick a lane to dim the others.</span>
  </div>
</header>

<nav aria-label="Phases">{rail_html}</nav>

<section class="panel" id="funnel">
  <h2>Focus funnel for the input dump</h2>
  <p>The agent never reads <code>00_inbox</code> as a whole. Code makes the dump small first; the agent then reads only named parts, and from P2 on it works from the brief and the evidence register. Numbers are from the S07 example.</p>
  <div class="funnel">
    <div class="fn" style="--i:0"><span><strong>00_inbox</strong> — every file as delivered: overviews, profiling workbooks, drafts, copies, emails, logos</span><span class="n">11 files</span></div>
    <div class="fn" style="--i:1"><span><strong>Inventory</strong> (code) — duplicates and version groups found, type suggested</span><span class="n">1 duplicate · 2 old versions</span></div>
    <div class="fn" style="--i:2"><span><strong>Triage</strong> — core / supporting / background / ignore</span><span class="n">4 / 1 / 2 / 4 · max 15 core</span></div>
    <div class="fn" style="--i:3"><span><strong>Read plan</strong> — only named sheets, pages, sections</span><span class="n">e.g. sheet LEGS only</span></div>
    <div class="fn" style="--i:4"><span><strong>Evidence register</strong> — one short claim per fact, with origin and confidence</span><span class="n">9 document claims · ≤40 words</span></div>
    <div class="fn" style="--i:5"><span><strong>Source brief</strong> — the page every later step reads</span><span class="n">158 words · ≤1800</span></div>
  </div>
</section>

<section class="panel" id="confidence">
  <h2>Confidence rules</h2>
  <p>Client profiling workbooks carry their own labels (High, Amber, 40%…). Code normalises them; the rules decide what each level may support.</p>
  <div class="conf">
    <div class="cf h"><b>high</b><span>Usable alone, unless bronze contradicts it. Labels: High, H, green, ≥ 80%.</span></div>
    <div class="cf m"><b>medium</b><span>Needs one corroboration: bronze, or a second document with authority ≤ 3. Amber, 50–79%.</span></div>
    <div class="cf l"><b>low</b><span>Hypothesis only. Verify in bronze or ask the client before it supports a key, FK, grain, or rule.</span></div>
    <div class="cf u"><b>unknown</b><span>No label. Treated as low.</span></div>
  </div>
  <p class="muted">Bronze wins for structure (keys, nulls, formats). Documents win for meaning (definitions, rules, codes). A client answer wins for both. The STTM validator refuses a PK, BK, FK, or business-logic column that rests only on low or unknown evidence.</p>
</section>

<section class="panel" id="phases">
  <h2>Phases, steps, and checkpoints</h2>
  {phases_html}
</section>

<section class="panel" id="discovery">
  <h2>Bronze discovery: code does the work, agents decide the rest</h2>
  <p>The largest piece of P2. Code finds keys, links, and roles with numbers as proof, on samples and with exact checks only for candidates. Judgement goes on small cards. Genie Code has no documented sub-agents, so each card is a self-contained task that any runtime can answer.</p>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Stage</th><th>Runs</th><th>Work</th><th>Output</th></tr></thead>
    <tbody>
      <tr><td>catalog + meta</td><td>code, once</td><td>tables, columns; Unity Catalog comments, owners, tags, masks, declared PK/FK, statistics, history; lineage system tables (who writes and reads)</td><td>parts/catalog.json, metadata/, lineage_view.json</td></tr>
      <tr><td>profile + keys</td><td>code, parallel per table</td><td>null %, approx distinct, shapes, value-kind ratios (email, phone, IP, user agent, token); minimal unique keys, exact check; values of sensitive columns removed before writing</td><td>columns.csv, keys.csv</td></tr>
      <tr><td>links</td><td>code, parallel per batch</td><td>distinct-value containment between columns, raw and normalised; cardinality</td><td>links.csv</td></tr>
      <tr><td>model</td><td>code, once</td><td>roles, grain, lineage levels, derived tables, ontology map; table scope; column class and scope (logs, audit, secrets, personal data)</td><td>tables.csv, column_scope.csv, graph.json, summary.md</td></tr>
      <tr><td>wider</td><td>code, once</td><td>tables outside the schema (names, shared key columns, lineage); documents vs bronze; same object in other sources</td><td>related.csv, doc_gaps.csv, overlap.csv</td></tr>
      <tr><td>cards</td><td>agents, one per card, parallel</td><td>decisions code cannot make (role, business object, scope, columns to confirm, partial links, aggregates; related tables; missing documented tables)</td><td>cards/T-, R-, D-xxx.result.yaml</td></tr>
      <tr><td>merge + evidence</td><td>code, once</td><td>apply answers, raise upstream issues, write evidence lines</td><td>tables.csv (final), FB items, E-ids</td></tr>
    </tbody></table></div>
  <p class="muted">Runtimes for cards: a Genie Code chat per card, or <code>tools/discovery/card_runner.py</code> (one fresh LLM call per card on a serving endpoint, answers checked), or later a Databricks multi-agent app / Agent Bricks supervisor with the card runner as a tool. Method: data-profiling literature (Abedjan, Golab, Naumann) and Kimball's grain and table roles.</p>
</section>

<section class="panel" id="input">
  <h2>Your input at every start and every review</h2>
  <p>The process is interactive. At the start of each checkpoint, and each time you type an instruction, give feedback, or upload a file, the input goes through the same four steps before any work starts.</p>
  <div class="life" aria-label="Input lifecycle">
    <span class="st">typed or uploaded</span><span class="arrow">→</span><span class="st block">checked against the ontology</span><span class="arrow">→</span><span class="st block">clarify: a few questions</span><span class="arrow">→</span><span class="st ok">route: steps that use it</span>
  </div>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Step</th><th>Who</th><th>What happens</th></tr></thead>
    <tbody>
      <tr><td>Capture</td><td>you, in <code>00_start_here</code></td><td><code>give-instruction</code> (IN-xxx, for a step or all), <code>give-feedback</code> (FB item), or files in <code>uploads/</code> + <code>register-uploads</code> (instruction, feedback, or handover to the next stage). A filled scope sheet is applied directly.</td></tr>
      <tr><td>Check</td><td>code: <code>x_input_ontology.py</code></td><td>Every term is matched to the <b>business</b> layer (objects, synonyms, abbreviations, relationships, rules), the <b>data</b> layer (classes, load patterns, bronze and silver tables and columns), and the <b>information</b> layer (phases, steps, checkpoints, evidence, questions). File headers and sheet names are read; values are not. Result: matches, unknown names, new concepts, conflicts (with instructions, evidence, relationships, business rules), intent, and route.</td></tr>
      <tr><td>Clarify</td><td>agent: <code>@x-clarify</code></td><td>Asks at most 7 questions, and only about unknowns, new concepts, conflicts, an unclear intent, or a rerun of approved work. A clear, known, conflict-free input gets no questions. "I don't know" becomes a client question.</td></tr>
      <tr><td>Route</td><td>code</td><td>Answers become instructions, evidence (<code>team_knowledge</code>, medium), feedback, client questions, or CP3 change requests. The input gets its route: the first step that uses it, and the checkpoints that go back to pending.</td></tr>
    </tbody></table></div>
</section>

<section class="panel" id="feedback">
  <h2>Feedback and rerun at any checkpoint</h2>
  <p>A reviewer does more than approve or reject. One feedback item <code>FB-xxxx.yaml</code> in <code>06_feedback/&lt;checkpoint&gt;/</code> can mix any of the kinds below. Code works out what to rerun, sets later checkpoints back to pending, and keeps the checkpoint blocked until the reviewer verifies the change.</p>
  <div class="life" aria-label="Feedback lifecycle">
    <span class="st block">open</span><span class="arrow">→</span><span class="st block">in_progress</span><span class="arrow">→ agent reruns →</span><span class="st block">applied</span><span class="arrow">→ reviewer checks →</span><span class="st ok">verified</span><span class="arrow">or</span><span class="st">rejected</span>
  </div>
  <p class="muted">Red states block approval of their checkpoint. Only the reviewer sets <code>verified</code> or <code>rejected</code>. Every agent run is logged to <code>run_log.jsonl</code>.</p>
  <div class="box">
    <span class="eyebrow">Upstream issues: an agent in a later phase finds a problem</span>
    <div class="life" aria-label="Upstream issue lifecycle"><span class="st">agent raises</span><span class="arrow">→</span><span class="st block">proposed</span><span class="arrow">→ person accepts →</span><span class="st block">open</span><span class="arrow">→ same loop as above</span></div>
    <p>The item sits on the earlier checkpoint that owns the problem and blocks the agent's own checkpoint (<code>--blocks</code>). The agent does not work around it. The third attempt for the same problem stops the gate: a person decides. All items: <code>registry/board/feedback_board.html</code>.</p>
<pre class="cli">python tools/x_feedback.py raise S07_container_moves CP1_source_brief --step p4-1-sttm-author \
  --comment "Brief grain key differs from bronze key" --blocks CP4_sttm
python tools/x_feedback.py accept FB-0003 --source S07_container_moves</pre>
  </div>
  <div class="two">
    <div class="tbl-wrap"><table>
      <thead><tr><th>Kind</th><th>Example</th><th>Used by</th></tr></thead>
      <tbody>
        <tr><td><code>comment</code></td><td>“ETA text is local port time.”</td><td>any step</td></tr>
        <tr><td><code>include_paths</code></td><td><code>00_inbox/03_Workshops/</code></td><td>P1.2, P2.3</td></tr>
        <tr><td><code>ignore_paths</code></td><td><code>00_inbox/Archive/</code></td><td>P1.2</td></tr>
        <tr><td><code>code</code></td><td>PySpark snippet for a cell or transform</td><td>P4.1, P5.1</td></tr>
        <tr><td><code>data</code></td><td>table + filter + columns to test</td><td>P2.2 (targeted check), P5.2</td></tr>
        <tr><td><code>attachments</code></td><td>port time-zone list (new file)</td><td>P1.1, P2.3</td></tr>
        <tr><td><code>answer</code></td><td>answer to Q-0001</td><td>P2.3</td></tr>
      </tbody></table></div>
    <div class="box">
      <span class="eyebrow">Example: feedback at CP2 for S07</span>
<pre class="cli">python tools/x_feedback.py new S07_container_moves CP2_evidence \\
  --comment "ETA text is local port time" \\
  --include 00_inbox/03_Workshops/ \\
  --data-table bronze.container_track.legs \\
  --data-filter "ETA_TS like '%/%'" \\
  --rerun-from p2-2-bronze-discovery

python tools/x_feedback.py plan  FB-0004 --source S07_container_moves
python tools/x_feedback.py reset FB-0004 --source S07_container_moves
#  agent reruns p2-2, p2-3 → validators recheck P4…P6
python tools/x_feedback.py set FB-0004 applied --source S07_container_moves \\
  --summary "E-0008 now client_answer, high" --changed 02_evidence/evidence_register.csv
python tools/x_feedback.py set FB-0004 verified --source S07_container_moves --by reviewer1</pre>
    </div>
  </div>
</section>

<section class="panel" id="ontology">
  <h2>Ontology: three layers, one chain</h2>
  <p>The ontology keeps 30 sources coherent. Every silver table names a business object and a data class, every FK follows a business relationship, and every column traces down to evidence and its origin.</p>
  <div class="layers">
    <div class="box layer b"><span class="eyebrow">Layer 1 · business.yaml</span><h3>Business</h3><ul>
      <li>Domains: PROC, COST, LOGI, SAVE, ORG</li><li>Processes, e.g. P-LOGI-02 track container legs</li>
      <li>Business objects + synonyms (Supplier ← vendor, provider)</li><li>Relationships R01–R17 with cardinality</li><li>Business rules BR-xxx-nnn (CP4b)</li></ul></div>
    <div class="box layer d"><span class="eyebrow">Layer 2 · data.yaml</span><h3>Data</h3><ul>
      <li>Data classes: master, reference, event, agreement, measure, snapshot, bridge</li><li>Allowed load patterns per class</li>
      <li>Conformed classes = shared entities</li><li>Key types BK, SK, FK; grain rule</li></ul></div>
    <div class="box layer i"><span class="eyebrow">Layer 3 · information.yaml</span><h3>Information</h3><ul>
      <li>Document types with authority</li><li>Relevance + reading rules + budgets</li>
      <li>Evidence origin, confidence, status</li><li>Phases, checkpoints, handovers</li></ul></div>
  </div>
  <div class="chain" aria-label="Lineage chain for one column">
    <div class="link layer-b"><span class="lvl">Business object</span><span class="src">business.yaml</span><span class="ex">ShipmentLeg (event) — R10 moves Container</span></div>
    <div class="link layer-d"><span class="lvl">Silver table + class</span><span class="src">sttm.yaml + data.yaml</span><span class="ex">slv_cnt_shipment_leg · event · merge</span></div>
    <div class="link layer-d"><span class="lvl">Silver column</span><span class="src">sttm.yaml column</span><span class="ex">container_sk · FK → Container</span></div>
    <div class="link layer-d"><span class="lvl">Bronze column</span><span class="src">sttm.yaml source</span><span class="ex">bronze.container_track.legs.CNTR_NO</span></div>
    <div class="link layer-i"><span class="lvl">Evidence</span><span class="src">evidence_register.csv</span><span class="ex">E-0001, E-0002 · high · confirmed_by_bronze</span></div>
    <div class="link layer-i"><span class="lvl">Origin</span><span class="src">manifest / 02_evidence</span><span class="ex">IF-0004 sheet LEGS row 4 · 02_evidence/discovery/links.csv</span></div>
  </div>
  <p class="muted">Checked by <code>x_ontology_check.py</code> (all layers together) and <code>p4_2_validate_sttm.py</code> (each STTM). A missing link fails the PR.</p>
</section>

<section class="panel" id="folders">
  <h2>Folders: folder number = phase number</h2>
  <p>Every phase folder has a <code>README.md</code>, a <code>checkpoint/</code> folder for its pack, and a <code>feedback/&lt;CP&gt;/</code> folder. P3 is global and lives in <code>registry/</code>. Code and QA live in <code>05_build/</code>, shared code in <code>lib/</code>, the QA checklist in <code>standards/</code>, PR checks in <code>.github/</code>.</p>
  <div class="tbl-wrap"><table>
    <thead><tr><th>Folder</th><th>Phase</th><th>Holds</th><th>Checkpoint pack</th></tr></thead>
    <tbody>
      <tr><td><code>00_inbox/</code></td><td>input</td><td>the dump, never edited</td><td>-</td></tr>
      <tr><td><code>01_intake/</code></td><td>P1</td><td>manifest, triage, source brief</td><td>CP1</td></tr>
      <tr><td><code>02_evidence/</code></td><td>P2</td><td>evidence register, <code>profiling/</code>, <code>discovery/</code> (+ cards)</td><td>CP2</td></tr>
      <tr><td><code>registry/</code></td><td>P3 (global)</td><td>ontology, entities, key rules, change requests, board</td><td>CP3, CP3b</td></tr>
      <tr><td><code>04_mapping/</code></td><td>P4</td><td>sttm.yaml, exports/, reviews/</td><td>CP4, CP4b</td></tr>
      <tr><td><code>05_build/</code></td><td>P5</td><td>notebooks, job, qa_results/, reviews/</td><td>CP5</td></tr>
      <tr><td><code>06_handoff/</code></td><td>P6</td><td>readiness.md</td><td>CP6</td></tr>
      <tr><td><code>masters/</code></td><td>P5 (global)</td><td>one build per shared master: survivorship across sources, unknown member, QA</td><td>via CP5 of feeding sources</td></tr>
    </tbody></table></div>
</section>

<footer>Source of truth: <code>registry/ontology/information.yaml</code> (phases, checkpoints, handovers) and <code>tools/x_feedback.py</code> (step catalogue and rerun plans). Example sources S01 and S07 are fictional.</footer>
</div>

<script>
(function () {{
  var keys = document.querySelectorAll(".key");
  keys.forEach(function (k) {{
    k.addEventListener("click", function () {{
      var f = k.getAttribute("data-focus");
      document.body.classList.remove("focus-agent", "focus-code", "focus-human");
      if (f) document.body.classList.add("focus-" + f);
      keys.forEach(function (x) {{ x.setAttribute("aria-pressed", x === k ? "true" : "false"); }});
    }});
  }});
}})();
</script>
'''

open(OUT_ART, "w", encoding="utf-8").write(BODY)
# standalone version for the repo
title_end = BODY.index("</title>") + len("</title>")
head_part, rest = BODY[:title_end], BODY[title_end:]
style_end = rest.index("</style>") + len("</style>")
standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
              '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
              + head_part + rest[:style_end] + "\n</head>\n<body>\n" + rest[style_end:] + "\n</body>\n</html>\n")
os.makedirs(os.path.join(KIT, "docs"), exist_ok=True)
open(os.path.join(KIT, "docs", "process_map.html"), "w", encoding="utf-8").write(standalone)
print("ok", len(BODY))
