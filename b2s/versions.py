"""Versioning through file names (design §7.5).

  <stem>.v<NNN>.<ext>          the version, write-once
  <stem>.v<NNN>.meta.json      sidecar: content hash, fingerprint, input versions, reason, event, framework version
  <stem>.v<NNN>.<other ext>    companions generated from that version (.mmd, .html, .xlsx); may be regenerated

A new version is written only when the content differs from the latest version. Latest = highest number.
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import FRAMEWORK_VERSION
from .layout import Layout
from .store import (atomic_write, current_user, dump_json, dump_yaml, emit_event, file_lock, load_any, now_iso,
                    sha256_bytes, write_once)

VER_RE = re.compile(r"^(?P<base>.+)\.v(?P<n>\d{3})\.(?P<ext>[A-Za-z0-9]+)$")


def vname(base: str, n: int, ext: str) -> str:
    return f"{base}.v{n:03d}.{ext}"


def vtag(n: int) -> str:
    return f"v{n:03d}"


@dataclass
class Version:
    stem: Path            # absolute path without .vNNN.ext
    n: int
    ext: str
    created: bool = True
    meta: dict = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.stem.parent / vname(self.stem.name, self.n, self.ext)

    @property
    def meta_path(self) -> Path:
        return self.stem.parent / f"{self.stem.name}.v{self.n:03d}.meta.json"

    def companion(self, ext: str) -> Path:
        return self.stem.parent / vname(self.stem.name, self.n, ext)

    @property
    def tag(self) -> str:
        return vtag(self.n)

    @property
    def label(self) -> str:
        """Short label used in approval statements, e.g. logical.v004"""
        return f"{self.stem.name}.{self.tag}"


def list_versions(stem: str | Path, ext: str) -> list[int]:
    stem = Path(stem)
    if not stem.parent.exists():
        return []
    out = []
    for f in stem.parent.iterdir():
        m = VER_RE.match(f.name)
        if m and m["base"] == stem.name and m["ext"] == ext:
            out.append(int(m["n"]))
    return sorted(out)


def find_ext(stem: str | Path) -> str | None:
    """Extension of the versioned main file of a stem (yaml, json, md ...), ignoring meta and companions."""
    stem = Path(stem)
    if not stem.parent.exists():
        return None
    for f in sorted(stem.parent.iterdir()):
        if f.name.startswith(stem.name + ".v") and f.name.endswith(".meta.json"):
            meta = json.loads(f.read_text(encoding="utf-8"))
            return meta.get("ext")
    return None


def latest(stem: str | Path, ext: str | None = None) -> Version | None:
    stem = Path(stem)
    ext = ext or find_ext(stem)
    if not ext:
        return None
    ns = list_versions(stem, ext)
    if not ns:
        return None
    return get(stem, ns[-1], ext)


def get(stem: str | Path, n: int, ext: str | None = None) -> Version | None:
    stem = Path(stem)
    ext = ext or find_ext(stem)
    v = Version(stem, n, ext, created=False)
    if not v.path.exists():
        return None
    if v.meta_path.exists():
        v.meta = json.loads(v.meta_path.read_text(encoding="utf-8"))
    return v


def read(v: Version):
    return load_any(v.path)


def serialise(content, ext: str) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    if ext == "json":
        return dump_json(content)
    if ext in ("yaml", "yml"):
        return dump_yaml(content)
    raise TypeError(f"cannot serialise {type(content)} as {ext}")


def save(layout: Layout, stem: str | Path, ext: str, content, *, reason: str, step: str | None = None,
         app: str | None = None, inputs: dict | None = None, fingerprint: str | None = None,
         extra_meta: dict | None = None, via: str | None = None) -> Version:
    """Save content as a new version if it differs from the latest one. Returns the (new or latest) version.

    inputs: {"<stem relative to app>": "v003", ...} — the exact input versions this content was made from (lineage).
    """
    stem = Path(stem)
    data = serialise(content, ext)
    h = sha256_bytes(data)
    with file_lock(layout, "ver-" + re.sub(r"[^A-Za-z0-9]+", "_", layout.rel(stem) if _inside(layout, stem) else str(stem))):
        cur = latest(stem, ext)
        if cur and cur.meta.get("content_hash") == h:
            # Same content: no new version, only an event (design §7.5). If the inputs changed but the output did not,
            # the sidecar records the new fingerprint so the output is no longer stale.
            emit_event(layout, "version_unchanged", app=app, step=step,
                       outputs={layout.rel(cur.path): h}, note=reason, via=via,
                       extra={"fingerprint": fingerprint, "inputs": inputs or {}})
            cur.created = False
            if fingerprint and cur.meta.get("fingerprint") != fingerprint:
                _refresh_fingerprint(layout, cur, fingerprint, inputs)
            return cur
        n = (cur.n + 1) if cur else 1
        v = Version(stem, n, ext, created=True)
        write_once(v.path, data)
        eid = emit_event(layout, "version_created", app=app, step=step, outputs={layout.rel(v.path): h},
                         note=reason, via=via, extra={"inputs": inputs or {}})
        meta = {"stem": layout.rel(stem), "version": v.tag, "n": n, "ext": ext, "content_hash": h,
                "fingerprint": fingerprint, "inputs": inputs or {}, "reason": reason, "step": step, "app": app,
                "framework_version": FRAMEWORK_VERSION, "created": {"at": now_iso(), "by": current_user(), "event": eid},
                "fingerprint_history": []}
        if extra_meta:
            meta.update(extra_meta)
        write_once(v.meta_path, dump_json(meta))
        v.meta = meta
        return v


def _refresh_fingerprint(layout: Layout, v: Version, fingerprint: str, inputs: dict | None) -> None:
    """The output did not change although its inputs did: the version stays, the sidecar records the new fingerprint
    (so it is no longer stale). History of fingerprints is kept inside the sidecar."""
    meta = dict(v.meta)
    meta.setdefault("fingerprint_history", []).append({"at": now_iso(), "fingerprint": meta.get("fingerprint"),
                                                       "inputs": meta.get("inputs")})
    meta["fingerprint"] = fingerprint
    if inputs is not None:
        meta["inputs"] = inputs
    atomic_write(v.meta_path, dump_json(meta))
    v.meta = meta


def _inside(layout: Layout, p: Path) -> bool:
    return layout.contains(p)


def write_companion(v: Version, ext: str, content) -> Path:
    """Generated file of the same version (.mmd, .html, .xlsx). Deterministic from the version, so it may be rewritten."""
    return atomic_write(v.companion(ext), serialise(content, ext) if not isinstance(content, bytes) else content)


def verify(v: Version) -> bool:
    """True if the version file still has the content hash recorded when it was written (tamper evidence)."""
    return sha256_bytes(v.path.read_bytes()) == v.meta.get("content_hash")


# --------------------------------------------------------------------------- diff
def diff(stem: str | Path, a: int, b: int, ext: str | None = None, max_lines: int = 40) -> dict:
    """Short change summary between two versions, for the chat before an approval."""
    va, vb = get(stem, a, ext), get(stem, b, ext)
    if not va or not vb:
        raise FileNotFoundError(f"version missing: {stem} v{a:03d} / v{b:03d}")
    ca, cb = read(va), read(vb)
    if isinstance(ca, (dict, list)) and isinstance(cb, (dict, list)):
        changes = _struct_diff(ca, cb)
        return {"from": va.label, "to": vb.label, "added": [c[1] for c in changes if c[0] == "+"],
                "removed": [c[1] for c in changes if c[0] == "-"], "changed": [c[1] for c in changes if c[0] == "~"]}
    lines = list(difflib.unified_diff(str(ca).splitlines(), str(cb).splitlines(), lineterm="", n=0))
    return {"from": va.label, "to": vb.label, "text": lines[:max_lines], "truncated": len(lines) > max_lines}


def _key(x):
    if isinstance(x, dict):
        for k in ("id", "name", "target_table", "table", "column", "target_column"):
            if k in x:
                return f"{k}={x[k]}"
    return None


def _struct_diff(a, b, path="") -> list:
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a.keys() - b.keys():
            out.append(("-", f"{path}/{k}"))
        for k in b.keys() - a.keys():
            out.append(("+", f"{path}/{k}"))
        for k in a.keys() & b.keys():
            out += _struct_diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list) and all(_key(x) for x in a + b):
        ka, kb = {_key(x): x for x in a}, {_key(x): x for x in b}
        for k in ka.keys() - kb.keys():
            out.append(("-", f"{path}[{k}]"))
        for k in kb.keys() - ka.keys():
            out.append(("+", f"{path}[{k}]"))
        for k in ka.keys() & kb.keys():
            out += _struct_diff(ka[k], kb[k], f"{path}[{k}]")
    elif a != b:
        out.append(("~", path or "/"))
    return out
