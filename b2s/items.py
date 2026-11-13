"""Knowledge items (design §6): one JSON file per item version, apps/<app>/items/<kind>/<id>.vNNN.json."""
from __future__ import annotations

from pathlib import Path

from . import versions
from .layout import Layout
from .store import current_user, current_via, next_id, now_iso, stable_id

# kind -> (id prefix, folder, sequential?)
KINDS = {
    "evidence":         ("E", "evidence", True),
    "question":         ("Q", "questions", True),
    "assumption":       ("A", "assumptions", True),
    "input":            ("IN", "inputs", True),
    "change_request":   ("CR", "change_requests", True),
    "document":         ("IF", "documents", True),
    "approval":         ("APR", "approvals", True),
    "open_point":       ("OP", "open_points", False),
}
PREFIX_TO_KIND = {v[0]: k for k, v in KINDS.items()}

STATUS = {
    "evidence": {"unverified", "corroborated", "confirmed_by_bronze", "contradicted", "superseded"},
    "question": {"open", "answered", "assumed", "withdrawn"},
    "assumption": {"active", "confirmed", "rejected"},
    "input": {"new", "traced", "routed", "applied", "closed"},
    "change_request": {"proposed", "approved", "applied", "dropped"},
    "document": {"registered", "triaged", "extracted"},
    "approval": {"recorded"},
    "open_point": {"open", "accepted", "changed", "question", "deferred", "resolved"},
}
DEFAULT_STATUS = {"evidence": "unverified", "question": "open", "assumption": "active", "input": "new",
                  "change_request": "proposed", "document": "registered", "approval": "recorded", "open_point": "open"}
CONFIDENCE = {"high", "medium", "low", "unknown"}
ORIGIN_TYPES = {"document", "bronze", "glean", "client_answer", "team_knowledge", "worker", "tool"}


class ItemError(ValueError):
    pass


def kind_of(item_id: str) -> str:
    prefix = item_id.split("-")[0]
    if prefix not in PREFIX_TO_KIND:
        raise ItemError(f"unknown item prefix: {item_id}")
    return PREFIX_TO_KIND[prefix]


def bucket(item_id: str) -> str:
    """E-0123 -> E-01xx (100 ids per folder); OP-3f9a2c -> OP-3f (hash ids by first two characters)."""
    prefix, rest = item_id.split("-", 1)
    return f"{prefix}-{rest[:-2]}xx" if rest.isdigit() else f"{prefix}-{rest[:2]}"


def _stem(layout: Layout, app: str, kind: str, item_id: str) -> Path:
    return layout.state_dir_app(app) / "items" / KINDS[kind][1] / bucket(item_id) / item_id


RESERVED = {"id", "kind", "app", "created", "updated"}


def _no_reserved(fields: dict) -> None:
    bad = RESERVED & fields.keys()
    if bad:
        raise ItemError(f"reserved field names in item fields: {sorted(bad)}")


def _validate(kind: str, item: dict) -> None:
    st = item.get("status")
    if st not in STATUS[kind]:
        raise ItemError(f"{item.get('id')}: status {st!r} not in {sorted(STATUS[kind])}")
    if kind == "evidence":
        if item.get("confidence") not in CONFIDENCE:
            raise ItemError(f"{item['id']}: confidence must be one of {sorted(CONFIDENCE)}")
        origin = item.get("origin") or {}
        if origin.get("type") not in ORIGIN_TYPES:
            raise ItemError(f"{item['id']}: origin.type must be one of {sorted(ORIGIN_TYPES)}")
        if not item.get("root_source"):
            raise ItemError(f"{item['id']}: root_source is required (DC-05)")
        if origin.get("type") == "glean" and item.get("confidence") == "high":
            raise ItemError(f"{item['id']}: a Glean claim is medium confidence at most (design §10.2)")
    if kind == "assumption" and not item.get("statement"):
        raise ItemError(f"{item['id']}: an assumption needs a statement")
    if kind == "question" and not item.get("text"):
        raise ItemError(f"{item['id']}: a question needs a text")


def create(layout: Layout, app: str, kind: str, fields: dict, *, step: str | None = None,
           reason: str = "first", via: str | None = None, identity=None) -> dict:
    """Create an item (version v001). Sequential id, or stable hash id from `identity` for derived kinds."""
    if kind not in KINDS:
        raise ItemError(f"unknown kind {kind}")
    _no_reserved(fields)
    prefix, _, sequential = KINDS[kind]
    item_id = next_id(layout, prefix) if sequential else stable_id(prefix, identity if identity is not None else fields)
    item = {**fields, "id": item_id, "kind": kind, "app": app,
            "created": {"at": now_iso(), "by": current_user(), "via": via or current_via()}}
    item.setdefault("status", DEFAULT_STATUS[kind])
    _validate(kind, item)
    versions.save(layout, _stem(layout, app, kind, item_id), "json", item, reason=reason, step=step, app=app, via=via)
    return item


def upsert_derived(layout: Layout, app: str, kind: str, identity, fields: dict, *, step: str | None = None,
                   reason: str = "rerun") -> tuple[dict, bool]:
    """For items code derives on each run (open points): stable id from identity; new version only if content changed.
    The worker's decision fields (status, decision, note) are kept from the latest version."""
    prefix = KINDS[kind][0]
    item_id = stable_id(prefix, identity)
    cur = get(layout, app, item_id)
    if cur is None:
        return create(layout, app, kind, fields, step=step, identity=identity, reason="first"), True
    _no_reserved(fields)
    keep = {k: cur[k] for k in ("status", "decision", "note", "created") if k in cur}
    new = {**fields, **keep, "id": item_id, "kind": kind, "app": app}
    _validate(kind, new)
    v = versions.save(layout, _stem(layout, app, kind, item_id), "json", new, reason=reason, step=step, app=app)
    return new, v.created


def get(layout: Layout, app: str, item_id: str, version: int | None = None) -> dict | None:
    stem = _stem(layout, app, kind_of(item_id), item_id)
    v = versions.get(stem, version, "json") if version else versions.latest(stem, "json")
    return versions.read(v) if v else None


def get_version(layout: Layout, app: str, item_id: str) -> versions.Version | None:
    return versions.latest(_stem(layout, app, kind_of(item_id), item_id), "json")


def update(layout: Layout, app: str, item_id: str, changes: dict, *, reason: str, step: str | None = None,
           via: str | None = None) -> dict:
    """New version of an item with changed fields. Never edits a version file."""
    cur = get(layout, app, item_id)
    if cur is None:
        raise ItemError(f"no such item {item_id} in {app}")
    _no_reserved(changes)
    new = {**cur, **changes}
    new["updated"] = {"at": now_iso(), "by": current_user(), "via": via or current_via(), "reason": reason}
    _validate(cur["kind"], new)
    versions.save(layout, _stem(layout, app, cur["kind"], item_id), "json", new, reason=reason, step=step, app=app, via=via)
    return new


def list_items(layout: Layout, app: str, kind: str, **filters) -> list[dict]:
    folder = layout.state_dir_app(app) / "items" / KINDS[kind][1]
    if not folder.exists():
        return []
    ids = sorted({f.name.split(".v")[0] for b in folder.iterdir() if b.is_dir() for f in b.iterdir()
                  if versions.VER_RE.match(f.name) and f.name.endswith(".json") and not f.name.endswith(".meta.json")})
    out = []
    for i in ids:
        it = get(layout, app, i)
        if it and all(it.get(k) == v for k, v in filters.items()):
            out.append(it)
    return out


def missing_refs(layout: Layout, app: str, obj) -> list[str]:
    """Ids in 'assumption' / 'question' / 'change_request' fields (anywhere in obj) that are not items of the app."""
    refs = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("assumption", "question", "change_request") and isinstance(v, str):
                    refs.add(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return sorted(r for r in refs if get(layout, app, r) is None)


def corroborated(evidence: list[dict]) -> bool:
    """Two or more claims count as corroboration only if they come from different root sources (DC-05),
    and a 'proposed' document alone never corroborates (DC-13)."""
    roots = {e["root_source"] for e in evidence if e.get("authority_class") != "proposed"}
    return len(roots) >= 2
