"""Glean protocol (design §10): conceptual rounds first, column rounds only for columns the framework could not explain.

Files per round: apps/<app>/research/GR-nnnn/
  request.json          write-once: topics, budget, type
  round.vNNN.json       state: drafted | sent | replied | parsed | integrated | closed | reopened (versioned)
  reply.raw.txt         write-once, saved FIRST, exactly as received (DC-04); reopened rounds use reply.raw.2.txt ...
  reply.json            parsed reply (write-once per raw reply)
Two channels write the same files: the Glean connector in Genie, or paste mode (a person pastes request and reply).
"""
from __future__ import annotations

import json

from . import items, versions
from .columns import unclear_columns
from .layout import Layout
from .store import dump_json, emit_event, load_any, next_id, now_iso, sha256_bytes, write_once

TYPES = ("conceptual", "conceptual_followup", "column")


class ResearchError(ValueError):
    pass


def _dir(layout: Layout, app: str, gr: str):
    return layout.stem(app, f"research/{gr}")


def _state(layout, app, gr) -> dict:
    v = versions.latest(_dir(layout, app, gr) / "round", "json")
    if not v:
        raise ResearchError(f"no research round {gr}")
    return versions.read(v)


def _set_state(layout, app, gr, state: dict, reason: str) -> dict:
    versions.save(layout, _dir(layout, app, gr) / "round", "json", state, reason=reason, app=app, step="research")
    return state


def rounds(layout: Layout, app: str, type_: str | None = None, status: str | None = None) -> list[dict]:
    root = layout.stem(app, "research/x").parent
    if not root.exists():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name.startswith("GR-"):
            s = _state(layout, app, d.name)
            if (type_ is None or s["type"] == type_) and (status is None or s["status"] == status):
                out.append(s)
    return out


def new_round(layout: Layout, app: str, type_: str, topics: list[dict], *, budget: int = 5, via: str | None = None) -> dict:
    """topics: [{"topic": "...", "question": "...", "about": "<table.column>" (column rounds)}]. One JSON object per topic."""
    if type_ not in TYPES:
        raise ResearchError(f"type must be one of {TYPES}")
    if not topics:
        raise ResearchError("a round needs at least one topic")
    if len(topics) > budget:
        raise ResearchError(f"{len(topics)} topics exceed the budget of {budget}; split the round or raise the budget with a reason")
    if type_ == "column":
        if not rounds(layout, app, status="integrated") or not any(r["type"].startswith("conceptual")
                                                                   for r in rounds(layout, app, status="integrated")):
            raise ResearchError("column rounds come after a conceptual round is integrated (ask Glean what the "
                                "application does and how it depends on other systems first)")
        unclear = unclear_columns(layout, app)
        bad = [t.get("about") for t in topics if t.get("about") not in unclear]
        if bad:
            raise ResearchError("ask Glean only about columns the framework marks unclear (run P6 first). "
                                f"Not unclear: {', '.join(str(b) for b in bad)}")
    gr = next_id(layout, "GR")
    req = {"id": gr, "app": app, "type": type_, "budget": budget, "created": now_iso(),
           "topics": [{"n": i + 1, **t} for i, t in enumerate(topics)],
           "instructions": "Answer each topic separately as one JSON object: {\"n\": <topic number>, \"answer\": \"...\", "
                           "\"sources\": [\"<document title or link>\"]}. Say 'unknown' when you do not know."}
    write_once(_dir(layout, app, gr) / "request.json", dump_json(req))
    _set_state(layout, app, gr, {"id": gr, "type": type_, "status": "drafted", "raw_replies": [], "budget": budget},
               "drafted")
    emit_event(layout, "research_round_created", app=app, items=[gr], via=via, note=type_)
    return req


def request_text(layout: Layout, app: str, gr: str) -> str:
    """The text to send to Glean (connector) or to paste (paste mode)."""
    req = load_any(_dir(layout, app, gr) / "request.json")
    return json.dumps({"instructions": req["instructions"],
                       "topics": [{"n": t["n"], "question": t["question"]} for t in req["topics"]]}, indent=2)


def mark_sent(layout: Layout, app: str, gr: str, channel: str) -> dict:
    if channel not in ("connector", "paste"):
        raise ResearchError("channel is connector or paste")
    s = _state(layout, app, gr)
    s.update(status="sent", channel=channel, sent=now_iso())
    return _set_state(layout, app, gr, s, f"sent via {channel}")


def record_raw(layout: Layout, app: str, gr: str, raw: str, *, channel: str = "paste", via: str | None = None) -> dict:
    """Save the raw reply FIRST, exactly as received. Nothing is parsed here."""
    if not raw or not raw.strip():
        raise ResearchError("the raw reply is empty; nothing saved")
    s = _state(layout, app, gr)
    n = len(s["raw_replies"]) + 1
    name = "reply.raw.txt" if n == 1 else f"reply.raw.{n}.txt"
    data = raw.encode("utf-8")
    write_once(_dir(layout, app, gr) / name, data)
    s["raw_replies"].append({"file": name, "hash": sha256_bytes(data), "at": now_iso(), "channel": channel})
    s["status"] = "replied"
    emit_event(layout, "research_reply_saved", app=app, items=[gr], via=via, note=name)
    return _set_state(layout, app, gr, s, f"raw reply {name}")


def parse(layout: Layout, app: str, gr: str, parsed: list[dict] | None = None) -> dict:
    """Parse the latest raw reply. Refuses when no non-empty raw reply exists (DC-04).
    `parsed` may be given by Genie (its reading of the reply); otherwise JSON objects are extracted from the raw text."""
    s = _state(layout, app, gr)
    if not s["raw_replies"]:
        raise ResearchError("no raw reply saved: save the reply first (record_raw), then parse")
    last = s["raw_replies"][-1]
    raw_path = _dir(layout, app, gr) / last["file"]
    raw = raw_path.read_text(encoding="utf-8")
    if not raw.strip() or sha256_bytes(raw.encode("utf-8")) != last["hash"]:
        raise ResearchError(f"raw reply {last['file']} is empty or changed since it was saved")
    answers = parsed if parsed is not None else _extract_json_objects(raw)
    out = {"from": last["file"], "raw_hash": last["hash"], "answers": answers}
    write_once(_dir(layout, app, gr) / last["file"].replace(".raw", "").replace(".txt", ".json"), dump_json(out))
    s["status"] = "parsed"
    _set_state(layout, app, gr, s, "parsed")
    return out


def _extract_json_objects(text: str) -> list[dict]:
    out, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict) and "n" in obj:
                        out.append(obj)
                except json.JSONDecodeError:
                    pass
    return out


def integrate(layout: Layout, app: str, gr: str, claims: list[dict], *, via: str | None = None) -> list[str]:
    """Turn claims from a parsed reply into evidence. claims: [{"statement", "about": [...], "cites": "IF-0021"|None}].
    Origin glean, root_source = the cited document (DC-05) or glean:GR-nnnn; confidence medium at most."""
    s = _state(layout, app, gr)
    if s["status"] not in ("parsed", "integrated"):
        raise ResearchError("parse the reply before integrating it")
    ids = []
    for c in claims:
        e = items.create(layout, app, "evidence", {
            "statement": c["statement"], "about": c.get("about") or [], "confidence": c.get("confidence", "medium")
            if c.get("confidence") != "high" else "medium",
            "origin": {"type": "glean", "ref": gr, "location": c.get("topic")},
            "root_source": c.get("cites") or f"glean:{gr}"}, via=via, step="research")
        ids.append(e["id"])
    s.update(status="integrated", evidence=s.get("evidence", []) + ids)
    _set_state(layout, app, gr, s, f"integrated {len(ids)} claims")
    return ids


def close(layout: Layout, app: str, gr: str) -> dict:
    s = _state(layout, app, gr)
    s["status"] = "closed"
    return _set_state(layout, app, gr, s, "closed")


def reopen(layout: Layout, app: str, gr: str, *, reason: str, extra_budget: int) -> dict:
    """A closed round can reopen with a reason and an extra budget (C-42)."""
    if not reason.strip():
        raise ResearchError("reopening needs a reason")
    s = _state(layout, app, gr)
    s.update(status="reopened", budget=s["budget"] + extra_budget,
             reopened=s.get("reopened", []) + [{"at": now_iso(), "reason": reason, "extra_budget": extra_budget}])
    emit_event(layout, "research_round_reopened", app=app, items=[gr], note=reason)
    return _set_state(layout, app, gr, s, f"reopened: {reason}")
