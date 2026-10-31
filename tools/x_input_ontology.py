#!/usr/bin/env python3
"""Understand one new input (typed text, uploaded file, new rule) against the three ontology levels, then route it.

    python tools/x_input_ontology.py S07_container_moves IN-003       # or FB-S07-k2q9

What it does (code, no LLM; the agent @x-clarify thinks on top of it):
  1. Read the input text and the files it names (only names, headers, sheet names, and text; never data values).
  2. Match every term to the ontology:
       business     business objects, synonyms, abbreviations, relationships (R..), business rules (BR-..), processes, domains
       data         data classes, load patterns, key types, silver tables and columns of this source, bronze tables and columns
       information  phases, steps, checkpoints, evidence (E-..), questions (Q-..), feedback (FB-..), instructions (IN-..), document types
  3. Find what is UNKNOWN (no match on any level), NEW (a business word that is not in the ontology), and in CONFLICT
     (with an active instruction, with strong evidence, or with a relationship's cardinality).
  4. Find the INTENT (scope, privacy, key rule, business rule, meaning, history, mapping, quality, document) and the ROUTE:
     the earliest step that must use the input, the checkpoints that go back to pending, and if a CP3 change request is needed.
  5. Make questions ONLY for unknowns, new concepts, conflicts, an unclear intent, and a rerun of approved work.
     Matched, clear, conflict-free input gets no questions.
Output: dict (also written by x_clarify to <phase>/clarify/IA-<ref>.yaml).
"""
from __future__ import annotations

import csv
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# intent -> (keywords, earliest step, ontology level it changes)
INTENTS = {
    "document":       (r"\b(latest|newer|older|version|draft|ignore (the )?file|use (the )?file|read (the )?file|workshop|minutes)\b", "p1-2-triage", "information"),
    "scope":          (r"\b(leave\b[\w ]{0,40}\bout|keep\b[\w ]{0,40}\bout of|exclude|not needed|out of scope|in scope|include|ignore|drop|skip|do not load|don't load|only load)\b", "p2-2-bronze-discovery", "data"),
    "privacy":        (r"\b(mask|hash|pii|personal|gdpr|confidential|sensitive|anonymi[sz]e|pseudonymi[sz]e)\b", "p2-2-bronze-discovery", "data"),
    "meaning":        (r"\b(means|meaning|is the|refers to|stands for|definition|defined as|one row (is|per)|grain)\b|\b[a-z][a-z0-9_]{2,} (is|are) (a|an|the|in|local|always|never)\b", "p2-3-evidence-reconcile", "business"),
    "key_rule":       (r"\b(leading zeros?|pad|lpad|trim|upper ?case|lower ?case|format of the key|key format|business key|natural key|normali[sz]e)\b", "p3-1-entity-model", "data"),
    "business_rule":  (r"\b(calculate|calculated|formula|rule|derive|sum of|average|times|multiplied|divided|=)\b", "p3-1-entity-model", "business"),
    "relationship":   (r"\b(belongs to|ha(s|ve) (many|one)|in many|one to many|many to one|many to many|1:n|n:1|n:m|m:n|parent|child)\b", "p3-1-entity-model", "business"),
    "history":        (r"\b(history|scd ?2?|late[- ]arriving|effective (from|date)|valid from|backdate|snapshot)\b", "p4-1-sttm-author", "data"),
    "mapping":        (r"\b(map|mapping|target column|source column|rename|convert|cast|time ?zone|utc|local\b[\w ]{0,15}\btime|unit)\b", "p4-1-sttm-author", "data"),
    "standard":       (r"\b(naming|naming rule|standard|convention|coding rule|qa checklist|checklist)\b", "p4-1-sttm-author", "information"),
    "quality":        (r"\b(check|qa|null|duplicate|reconcile|count|threshold|tolerance|orphan)\b", "p5-2-qa-runner", "data"),
}
NEG = r"\b(leave\b[\w ]{0,40}\bout|keep\b[\w ]{0,40}\bout of|exclude|not needed|out of scope|ignore|drop|do not|don't|never)\b"
STOP = set("""a an the and or not no of to in on for by with from at is are be was were this that these those it its as
if then than so do does did can could should would will must may might has have had please also only all any each
same new old we our you your they their there here when where which what who how why use using used into over under per
via about after before more less very just make sure""".split())


def _y(p):
    return yaml.safe_load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def _csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# ----------------------------------------------------------------------------- vocabulary of the three levels
def vocabulary(sid, root=ROOT):
    """{normalised term: [(level, kind, canonical)]} for business, data, and information."""
    import x_feedback as fb
    o = os.path.join(root, "registry", "ontology")
    bus, dat, inf = _y(os.path.join(o, "business.yaml")) or {}, _y(os.path.join(o, "data.yaml")) or {}, _y(os.path.join(o, "information.yaml")) or {}
    V = {}

    def add(term, level, kind, canon):
        k = _norm(term)
        if len(k) >= 2 and (level, kind, canon) not in V.setdefault(k, []):
            V[k].append((level, kind, canon))
    for name, d in (bus.get("business_objects") or {}).items():
        add(name, "business", "object", name)
        add(re.sub(r"(?<!^)(?=[A-Z])", " ", name), "business", "object", name)
        for syn in d.get("synonyms") or []:
            add(syn, "business", "synonym", name)
    for ab, word in (bus.get("abbreviations") or {}).items():
        objs = [n for n, d in (bus.get("business_objects") or {}).items()
                if _norm(word) in (_norm(n), *[_norm(s) for s in d.get("synonyms") or []])]
        add(ab, "business", "abbreviation", objs[0] if objs else word)
    for rid, r in (bus.get("relationships") or {}).items():
        add(rid, "business", "relationship", f"{r['subject']} {r['verb']} {r['object']} ({r['cardinality']})")
    for bid in (bus.get("business_rules") or {}):
        add(bid, "business", "business_rule", bid)
    for pid, p in (bus.get("processes") or {}).items():
        add(pid, "business", "process", p["name"])
    for did, d in (bus.get("domains") or {}).items():
        add(d["name"], "business", "domain", did)
    for cls, d in (dat.get("data_classes") or {}).items():
        add(cls, "data", "data_class", cls)
        for lp in d.get("allowed_load_patterns") or []:
            add(lp, "data", "load_pattern", lp)
    for kt in (dat.get("key_types") or {}):
        add(kt, "data", "key_type", kt)
    disc = os.path.join(root, "sources", sid, "02_evidence", "discovery")
    for r in _csv(os.path.join(disc, "tables.csv")):
        add(r["table"].split(".")[-1], "data", "bronze_table", r["table"])
    for r in _csv(os.path.join(disc, "column_scope.csv")) or _csv(os.path.join(disc, "columns.csv")):
        if r.get("column"):
            add(r["column"], "data", "bronze_column", f"{r['table'].split('.')[-1]}.{r['column']}")
    sttm = _y(os.path.join(root, "sources", sid, "04_mapping", "sttm.yaml")) or {}
    for t in sttm.get("tables") or []:
        tn = t.get("target_table") or t.get("name")
        add(tn, "data", "silver_table", tn)
        for c in t.get("columns") or []:
            add(c["target"], "data", "silver_column", f"{tn}.{c['target']}")
    for ent in ((_y(os.path.join(root, "registry", "entities.yaml")) or {}).get("entities") or {}):
        add(ent, "data", "conformed_entity", ent)
    for ph, d in (inf.get("phases") or {}).items():
        add(ph, "information", "phase", d["name"])
    for cp in (inf.get("checkpoints") or {}):
        add(cp, "information", "checkpoint", cp)
        add(cp.split("_")[0], "information", "checkpoint", cp)
    for s_, _, _ in fb.STEPS:
        add(s_, "information", "step", s_)
    for dt in (inf.get("document_types") or {}):
        add(dt, "information", "document_type", dt)
    for og in (inf.get("evidence_origins") or {}):
        add(og, "information", "evidence_origin", og)
    return V


def _ids(text):
    return re.findall(r"\b(?:E-\d{4}|Q-\d{4}|IN-\d{3}|FB-[A-Za-z0-9]+-[a-z0-9]{4}|FB-\d{4}|BR-[A-Z]+-\d{3}|R\d{2}|P-[A-Z]+-\d{2}|CP\d+b?)\b", text)


def _phrases(text):
    """Candidate terms: identifiers (with _ or digits or ALL CAPS), single words, and 2-word phrases."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]*", text)
    out = []
    for i, w in enumerate(words):
        out.append(w)
        if i + 1 < len(words) and w.lower() not in STOP and words[i + 1].lower() not in STOP:
            out.append(f"{w} {words[i + 1]}")
    return out


def _is_ident(w):
    return "_" in w or (w.isupper() and len(w) >= 3) or bool(re.search(r"[a-z][A-Z]", w)) or bool(re.search(r"\d", w))


# ----------------------------------------------------------------------------- files named in the input
def file_terms(paths, root=ROOT, sid=None):
    """Names, headers, sheet names, and text words of the attached files. Never data values (personal data stays out)."""
    out, notes = [], []
    for rel in paths:
        cands = [os.path.join(root, rel), os.path.join(root, "sources", sid or "", rel)]
        p = next((c for c in cands if os.path.isfile(c)), None)
        if not p:
            notes.append(f"{rel}: not found")
            continue
        ext = os.path.splitext(p)[1].lower()
        try:
            if ext in (".csv", ".tsv"):
                hdr = next(csv.reader(open(p, encoding="utf-8", errors="ignore"), delimiter="\t" if ext == ".tsv" else ","), [])
                out += hdr
                notes.append(f"{os.path.basename(p)}: table with columns {', '.join(hdr[:12])}")
            elif ext in (".xlsx", ".xlsm"):
                import openpyxl
                wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
                for ws in wb.worksheets[:10]:
                    hdr = [str(c) for c in next(ws.iter_rows(max_row=1, values_only=True), []) if c is not None]
                    out += [ws.title] + hdr
                    notes.append(f"{os.path.basename(p)} sheet {ws.title}: columns {', '.join(hdr[:12])}")
            elif ext in (".txt", ".md", ".yaml", ".yml", ".json", ".sql", ".py"):
                txt = open(p, encoding="utf-8", errors="ignore").read()[:20000]
                out.append(txt)
                notes.append(f"{os.path.basename(p)}: text, {len(txt.split())} words")
            else:
                notes.append(f"{os.path.basename(p)}: {ext or 'no extension'} file (not read by code: the agent opens it)")
        except Exception as e:  # noqa: BLE001
            notes.append(f"{os.path.basename(p)}: cannot read ({type(e).__name__})")
    return out, notes


# ----------------------------------------------------------------------------- analysis
def analyse(sid, ref, text, files=None, kind="instruction", target=None, root=ROOT):
    import x_feedback as fb
    import x_navigator as nav
    files = list(files or []) + re.findall(r"\buploads/[^\s,;]+", text)
    ftexts, fnotes = file_terms(sorted(set(files)), root, sid)
    full = " ".join([text] + ftexts)
    V = vocabulary(sid, root)
    matched, unknown, new = {}, [], []
    for ph in _phrases(full) + _ids(full):
        k = _norm(ph)
        if k in V and len(k) >= 3:
            for lv, kd, canon in V[k]:
                matched.setdefault((lv, kd, canon), set()).add(ph)
    known_words = {w.lower() for v in matched.values() for p in v for w in p.split()}
    for w in set(re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", " ".join([text] + [t for t in ftexts if len(t) < 80]))):
        if w.lower() in STOP or w.lower() in known_words or _norm(w) in V:
            continue
        if _is_ident(w):
            unknown.append(w)
    for i in _ids(text):
        if _norm(i) not in V and not re.match(r"(E|Q|IN|FB)-", i):
            unknown.append(i)
    # a business word in the input that looks like a thing (noun before 'is a', 'are', 'table', 'object') and is not known
    for m in re.finditer(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) (?:is an?|are|object|entity|master)\b", text):
        if _norm(m.group(1)) not in V and m.group(1).lower() not in STOP:
            new.append(m.group(1))
    levels = {"business": [], "data": [], "information": []}
    for (lv, kd, canon), phs in sorted(matched.items()):
        levels[lv].append({"kind": kd, "match": canon, "said": sorted(phs)[:3]})
    low = full.lower()
    intents = [n for n, (rx, _, _) in INTENTS.items() if re.search(rx, low)]
    # route: earliest affected step; compare with progress
    order = [s for s, _, _ in fb.STEPS]
    first = min((INTENTS[i][1] for i in intents), key=order.index, default=None)
    if any(d["kind"] in ("relationship", "business_rule") for d in levels["business"]) and "p3-1-entity-model" not in [first]:
        first = min([x for x in [first, "p3-1-entity-model"] if x], key=order.index)
    if kind == "instruction" and target and target != "all" and target in order:
        first = target if not first else min([first, target], key=order.index)
    info = nav.steps(sid, root)
    cur = info["checkpoint"]
    step_cp = {s: c for s, _, c in fb.STEPS}
    status = info["status"]
    rerun = bool(first) and status.get(step_cp[first]) in ("approved", "in_review")
    pl = fb.plan({"checkpoint": step_cp[first], "rerun_from": first}) if first else None
    cr = []
    if new:
        cr.append(f"new business object(s) {', '.join(sorted(set(new)))}: change request at CP3")
    conflicts = _conflicts(sid, text, levels, intents, ref, root)
    for c in conflicts:
        if re.fullmatch(r"R\d{2}", c["with"]):
            cr.append(f"changes relationship {c['with']} in business.yaml: change request at CP3")
        if c["with"].startswith("BR-"):
            cr.append(f"may change business rule {c['with']}: change request at CP3 and sign-off at CP4b")
    if "business_rule" in intents and not any(d["kind"] == "business_rule" for d in levels["business"]) and \
            not any(c["with"].startswith("BR-") for c in conflicts) and \
            re.search(r"\b(calculate|formula|derive|sum of|=)\b", low):
        cr.append("a business rule that is not in business.yaml: change request at CP3 (and CP4b sign-off)")
    if "key_rule" in intents:
        cr.append("a key format rule: registry/key_normalisation.yaml, approved at CP3b")
    if "standard" in intents:
        cr.append("a client standard (standards/): the project lead changes it by PR; generators and QA of every source use it")
    route = {"earliest_step": first, "applies_from": step_cp.get(first) if first else None, "current_checkpoint": cur,
             "rerun_needed": rerun, "rerun_now": pl["rerun_now"] if pl and rerun else [],
             "reset_checkpoints": pl["reset_checkpoints"] if pl and rerun else [],
             "change_requests": cr, "global": bool(cr) or bool(re.search(r"\b(all|every|each) sources?\b", low))}
    return {"ref": ref, "kind": kind, "target": target, "intents": intents, "levels": levels,
            "unknown": sorted(set(unknown))[:15], "new_concepts": sorted(set(new)), "conflicts": conflicts,
            "files": fnotes, "route": route, "questions": _questions(ref, intents, unknown, new, conflicts, route, levels, text)}


def _conflicts(sid, text, levels, intents, ref, root):
    import x_navigator as nav
    out = []
    low = text.lower()
    # 1. other active instructions about the same thing with the opposite direction (include vs exclude)
    neg = bool(re.search(NEG, low))
    said = {_norm(p) for lv in levels.values() for d in lv for p in d["said"]}
    for i in nav.instructions(sid, root):
        if i["id"] == ref:
            continue
        it = i["text"].lower()
        ineg = bool(re.search(NEG, it))
        common = {w for w in said if w and w in _norm(it)}
        if common and neg != ineg:
            out.append({"with": i["id"], "about": sorted(common)[0], "kind": "opposite", "fact": f"{i['id']} says: {i['text'][:120]}"})
    # 2. strong evidence about the same bronze COLUMN (written as an identifier), when the input states a fact about it
    if set(intents) & {"meaning", "key_rule", "relationship", "mapping", "history"}:
        for r in _csv(os.path.join(root, "sources", sid, "02_evidence", "evidence_register.csv")):
            about = str(r.get("about", "")).split("->")[0].split(".")[-1].strip()
            if about and _is_ident(about) and re.search(rf"\b{re.escape(about)}\b", text) and r.get("status") in ("confirmed_by_bronze", "corroborated"):
                out.append({"with": r["evidence_id"], "about": about, "kind": "touches",
                            "fact": f"{r['evidence_id']} ({r['status']}): {r['claim']}"})
                break
    # 3. a stated cardinality that differs from the relationship in business.yaml
    m = re.search(r"\b(one|many|1|n|m)\s*(?:-|to|:)\s*(one|many|1|n|m)\b", low)
    rels = [d for d in levels["business"] if d["kind"] == "relationship"]
    objs = {d["match"] for d in levels["business"] if d["kind"] in ("object", "synonym", "abbreviation")}
    if m and len(objs) >= 2:
        say = "".join("N" if x in ("many", "n", "m") else "1" for x in m.groups())
        bus = _y(os.path.join(root, "registry", "ontology", "business.yaml")) or {}
        for rid, r in (bus.get("relationships") or {}).items():
            if {r["subject"], r["object"]} <= objs:
                card = r["cardinality"].upper().replace("M", "N").replace(":", "")
                if card not in (say, say[::-1]):
                    out.append({"with": rid, "about": f"{r['subject']}-{r['object']}", "kind": "opposite", "fact": f"{rid} says {r['subject']} {r['verb']} {r['object']} is {r['cardinality']}"})
    del rels
    # 4. a business rule whose subject (left of '=') the input talks about
    bus = _y(os.path.join(root, "registry", "ontology", "business.yaml")) or {}
    for bid, b in (bus.get("business_rules") or {}).items():
        lhs = str(b.get("desc", "")).split("=")[0].strip().lower()
        if lhs and len(lhs) >= 4 and lhs in low and bid not in text:
            out.append({"with": bid, "about": lhs, "kind": "touches", "fact": f"{bid} ({b.get('status')}): {b['desc']}"})
    return out


def _questions(ref, intents, unknown, new, conflicts, route, levels, text):
    """Only pertinent questions. Each: question, why, record_as."""
    Q = []
    for c in conflicts:
        if c.get("kind") == "touches":
            Q.append({"q": f"{ref} is about {c['about']}, and {c['fact']}. Does {ref} change or add to that? If it changes it, who confirmed it?",
                      "why": "the ontology or strong evidence already says something about it", "record_as": "evidence"})
        else:
            Q.append({"q": f"{ref} and {c['with']} do not agree about {c['about']} ({c['fact']}). Which one is right, and should the other change?",
                      "why": "a conflict changes the evidence, the ontology, or an earlier instruction", "record_as": "evidence"})
    if new:
        Q.append({"q": f"Is '{', '.join(new)}' a new business object (not in business.yaml)? If yes: what is one of it, and which objects does it relate to?",
                  "why": "a new object is a change to the business ontology (CP3)", "record_as": "change_request"})
    if unknown:
        Q.append({"q": f"I do not know these names: {', '.join(unknown[:6])}. For each: a bronze table or column (which schema?), a business term, or a typo?",
                  "why": "an unknown name cannot be traced through the ontology", "record_as": "instruction"})
    if not intents:
        Q.append({"q": f"What should change because of {ref}: scope, a mapping, a rule, a meaning, or the documents to read? How will you check it?",
                  "why": "the input does not say what to do", "record_as": "instruction"})
    if route["rerun_needed"]:
        Q.append({"q": f"This goes back to {route['earliest_step']} and puts {', '.join(route['reset_checkpoints'])} back to pending. Rerun now, or keep it for the next cycle?",
                  "why": "a rerun undoes approved work", "record_as": "feedback"})
    if route["change_requests"] and not new and not re.search(r"\b(all|every|each) sources?\b", text.lower()):
        cr0 = route["change_requests"][0]
        Q.append({"q": f"This {cr0.split(':')[0]} ({cr0.split(':', 1)[1].strip()}). Is it for this source only, or for all sources?",
                  "why": "a shared rule changes every source that uses it", "record_as": "change_request"})
    syn = [d for d in levels["business"] if d["kind"] in ("synonym", "abbreviation")]
    multi = {}
    for d in syn:
        for s_ in d["said"]:
            multi.setdefault(_norm(s_), set()).add(d["match"])
    for s_, objs in multi.items():
        if len(objs) > 1:
            Q.append({"q": f"'{s_}' can mean {', '.join(sorted(objs))}. Which one do you mean?",
                      "why": "one word maps to two business objects", "record_as": "instruction"})
    return Q[:7]


def to_yaml(a, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Input analysis (code). Matches to the business, data, and information ontology; unknowns; conflicts; route.\n")
        yaml.safe_dump(a, f, sort_keys=False, allow_unicode=True)


def main(argv=None):
    a = list(argv if argv is not None else sys.argv[1:])
    if len(a) < 2:
        print(__doc__)
        return 1
    import x_clarify as qz
    print(yaml.safe_dump(qz.analyse_ref(a[0], a[1]), sort_keys=False, allow_unicode=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
