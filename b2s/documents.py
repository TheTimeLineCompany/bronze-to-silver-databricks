"""P3 documents (design §5): inventory, triage, extract. Deterministic; the claims are written later by Genie.

inventory  every file in apps/<app>/inbox: hash, size, duplicates (keep the clean name), same name with different
           content ("compare"), unreadable files. One document item (IF-xxxx) per unique content.
triage     relevance core | supporting | background | ignore, from information.yaml document types and naming rules;
           a reading plan (headings only) for core and supporting files; at most budgets.max_core_files core files.
extract    text of core and supporting files, with personal data replaced by shapes (R-01).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import items, versions
from .layout import Layout
from .project import ontology
from .store import emit_event

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".svg", ".webp", ".heic"}
TEXT_EXT = {".md", ".txt", ".csv", ".sql"}
COPY_MARK = re.compile(r"(\(copy\)|\bcopy of\b|[ _-]copy\b|\(\d+\)$)", re.I)
OLD_MARK = re.compile(r"(^|[ _-])(old|draft|bak|backup|archive|superseded|v0)([ _.-]|$)", re.I)
VERSION_MARK = re.compile(r"[ _-]?v(\d+)$", re.I)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w])\+?\d[\d ()./-]{6,}\d(?![\w])")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DATE_LIKE = re.compile(r"^(\d{4}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]\d{2,4})$")


def _shape(s: str) -> str:
    return "".join("9" if c.isdigit() else ("a" if c.isalpha() else c) for c in s)


def redact_text(text: str) -> str:
    """Replace emails, phone numbers and IP addresses by their shapes."""
    text = EMAIL.sub(lambda m: _shape(m.group(0)), text)
    text = IPV4.sub(lambda m: _shape(m.group(0)), text)
    def phone(m):
        s = m.group(0)
        if sum(ch.isdigit() for ch in s) < 7 or DATE_LIKE.match(s):
            return s
        return _shape(s)
    return PHONE.sub(phone, text)


def _clean_score(rel: str) -> tuple:
    stem = Path(rel).stem
    return (bool(COPY_MARK.search(stem)), bool(OLD_MARK.search(stem)), len(Path(rel).parts), len(stem), rel)


def read_text(path: Path) -> str | None:
    """Text of a document, or None if no extractor can read it."""
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        if ext == ".docx":
            import docx
            d = docx.Document(str(path))
            return "\n".join(("# " if p.style.name.lower().startswith("heading") else "") + p.text for p in d.paragraphs)
        if ext == ".pptx":
            import pptx
            out = []
            for i, s in enumerate(pptx.Presentation(str(path)).slides, 1):
                title = s.shapes.title.text if s.shapes.title is not None else f"Slide {i}"
                out.append(f"# {title}")
                out += [sh.text_frame.text for sh in s.shapes if sh.has_text_frame and sh != s.shapes.title]
            return "\n".join(out)
        if ext == ".pdf":
            import pypdf
            text = "\n".join((pg.extract_text() or "") for pg in pypdf.PdfReader(str(path)).pages)
            return text if text.strip() else None
    except ImportError:
        return None
    except Exception:
        return None
    return None


def _readable(path: Path) -> tuple[bool, str | None]:
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return False, "image"
    if ext in TEXT_EXT:
        return True, None
    if ext in (".docx", ".pptx", ".pdf"):
        t = read_text(path)
        if t is None:
            return False, "image_only_pdf" if ext == ".pdf" else "needs_extractor"
        return True, None
    return False, "needs_extractor"


# =========================================================================== inventory
def inventory(layout: Layout, app: str) -> dict:
    inbox = layout.sub(app, "inbox")
    files = sorted(p for p in inbox.rglob("*") if p.is_file() and not p.name.startswith("."))
    recs = []
    for p in files:
        data = p.read_bytes()
        rel = p.relative_to(inbox).as_posix()
        ok, why = _readable(p)
        recs.append({"path": rel, "name": p.name, "ext": p.suffix.lower(), "size": len(data),
                     "sha256": hashlib.sha256(data).hexdigest(), "readable": ok, "unreadable_reason": why})
    by_sha: dict = {}
    for r in recs:
        by_sha.setdefault(r["sha256"], []).append(r)
    existing = {it.get("sha256"): it["id"] for it in items.list_items(layout, app, "document")}
    for sha, group in sorted(by_sha.items()):
        group.sort(key=lambda r: _clean_score(r["path"]))
        keep = group[0]
        if sha in existing:
            doc_id = existing[sha]
        else:
            doc_id = items.create(layout, app, "document", {
                "name": keep["name"], "path": keep["path"], "sha256": sha, "ext": keep["ext"], "size": keep["size"],
                "readable": keep["readable"], "duplicates": [r["path"] for r in group[1:]]}, step="P2.1")["id"]
            existing[sha] = doc_id
        for r in group:
            r["doc_id"] = doc_id
            r["duplicate_of"] = None if r is keep else keep["path"]
    by_name: dict = {}
    for r in recs:
        by_name.setdefault(r["name"].lower(), []).append(r)
    compare = []
    for name, group in sorted(by_name.items()):
        if len({r["sha256"] for r in group}) > 1:
            compare.append(sorted(r["path"] for r in group))
            for r in group:
                r["compare_with"] = sorted(x["path"] for x in group if x is not r)
    inv = {"app": app, "files": recs, "documents": len(by_sha),
           "duplicates": [r["path"] for r in recs if r["duplicate_of"]],
           "compare": compare, "unreadable": [{"path": r["path"], "reason": r["unreadable_reason"]} for r in recs
                                              if not r["readable"]]}
    v = versions.save(layout, layout.stem(app, "documents/inventory"), "json", inv, reason="inventory", step="P2.1",
                      app=app, inputs={"inbox": hashlib.sha256("".join(r["sha256"] for r in recs).encode()).hexdigest()[:16]})
    emit_event(layout, "documents_inventory", app=app, step="P2.1", outputs={layout.rel(v.path): v.meta.get("content_hash")},
               note=f"{len(recs)} files, {len(by_sha)} unique, {len(inv['unreadable'])} unreadable")
    inv["_version"] = v.label
    return inv


# =========================================================================== triage
def _headings(text: str, limit: int = 30) -> list[str]:
    hs = [l.strip().lstrip("#").strip() for l in text.splitlines() if l.lstrip().startswith("#")]
    if not hs:
        hs = [l.strip() for l in text.splitlines() if l.strip()][:5]
    return hs[:limit]


def _doc_type(name: str, text: str, types: dict) -> tuple[str | None, int]:
    hay = (name + "\n" + "\n".join(_headings(text or "", 10))).lower()
    best, score = None, 0
    for t, spec in types.items():
        s = sum(1 for sig in spec.get("signals") or [] if not sig.startswith(".") and sig.lower() in hay) + \
            sum(1 for sig in spec.get("signals") or [] if sig.startswith(".") and name.lower().endswith(sig.lower()))
        if s > score or (s == score and s and types[t].get("authority", 9) < types[best].get("authority", 9)):
            best, score = t, s
    return best, score


def triage(layout: Layout, app: str) -> dict:
    inv_v = versions.latest(layout.stem(app, "documents/inventory"), "json")
    if inv_v is None:
        raise FileNotFoundError("run documents.inventory first")
    inv = versions.read(inv_v)
    info = ontology(layout, "information")
    types = info.get("document_types") or {}
    max_core = int((info.get("budgets") or {}).get("max_core_files", 15))
    inbox = layout.sub(app, "inbox")
    # version groups: same base name without version/old/copy marks -> only the newest stays
    base_of = {}
    for r in inv["files"]:
        stem = Path(r["path"]).stem
        b = VERSION_MARK.sub("", OLD_MARK.sub(" ", COPY_MARK.sub("", stem))).strip(" _-").lower()
        base_of[r["path"]] = b
    out = []
    for r in inv["files"]:
        e = {"doc_id": r["doc_id"], "path": r["path"], "type": None, "authority": None, "relevance": None,
             "reason": None, "reading_plan": []}
        stem = Path(r["path"]).stem
        if r.get("duplicate_of"):
            e.update(relevance="ignore", reason=f"exact copy of {r['duplicate_of']}")
        elif COPY_MARK.search(stem) or OLD_MARK.search(stem) or OLD_MARK.search(Path(r["path"]).parent.as_posix() or ""):
            e.update(relevance="ignore", type="draft_or_superseded", reason="old version, draft or copy by its name")
        elif not r["readable"]:
            e.update(relevance="background", reason=f"unreadable ({r['unreadable_reason']}): needs an extractor or a person")
        else:
            text = read_text(inbox / r["path"]) or ""
            t, s = _doc_type(r["name"], text, types)
            spec = types.get(t) or {}
            e.update(type=t, authority=spec.get("authority"),
                     relevance=spec.get("default_relevance", "supporting") if s else "supporting",
                     reason=f"signals of {t}" if s else "no type signal")
            if e["relevance"] in ("core", "supporting"):
                e["reading_plan"] = _headings(text)
        out.append(e)
    core = [e for e in out if e["relevance"] == "core"]
    for e in sorted(core, key=lambda e: (e["authority"] or 9, e["path"]))[max_core:]:
        e.update(relevance="supporting", reason=(e["reason"] or "") + f"; core budget {max_core} reached")
    res = {"app": app, "inventory": inv_v.label, "max_core_files": max_core, "documents": out,
           "counts": {k: sum(e["relevance"] == k for e in out) for k in ("core", "supporting", "background", "ignore")}}
    v = versions.save(layout, layout.stem(app, "documents/triage"), "yaml", res, reason="triage", step="P2.1", app=app,
                      inputs={"documents/inventory": inv_v.tag})
    emit_event(layout, "documents_triage", app=app, step="P2.1", outputs={layout.rel(v.path): v.meta.get("content_hash")},
               note=str(res["counts"]))
    res["_version"] = v.label
    return res


# =========================================================================== extract
def extract(layout: Layout, app: str) -> dict:
    tv = versions.latest(layout.stem(app, "documents/triage"), "yaml")
    if tv is None:
        raise FileNotFoundError("run documents.triage first")
    tri = versions.read(tv)
    inbox = layout.sub(app, "inbox")
    res = {"extracted": [], "needs_extractor": [], "skipped": []}
    done = set()
    for e in tri["documents"]:
        if e["relevance"] not in ("core", "supporting") or e["doc_id"] in done:
            res["skipped"].append(e["path"])
            continue
        text = read_text(inbox / e["path"])
        if text is None:
            res["needs_extractor"].append(e["path"])
            continue
        body = f"<!-- {e['doc_id']} {e['path']} (redacted extract) -->\n" + redact_text(text)
        v = versions.save(layout, layout.stem(app, f"documents/extracts/{e['doc_id']}"), "md", body,
                          reason="extract", step="P2.1", app=app, inputs={"documents/triage": tv.tag})
        res["extracted"].append({"doc_id": e["doc_id"], "version": v.label})
        done.add(e["doc_id"])
    emit_event(layout, "documents_extract", app=app, step="P2.1",
               note=f"{len(res['extracted'])} extracted, {len(res['needs_extractor'])} need an extractor")
    return res
