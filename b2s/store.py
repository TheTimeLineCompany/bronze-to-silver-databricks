"""File state without tables (design §7): atomic writes, write-once files, locks, ids, events, leases.

Workspace files have no transactions and no row locks. The rules here make them safe enough:
  * write to a temporary name, then rename (atomic_write)
  * files that hold history are written once and never changed (write_once)
  * counters (ids, version numbers) change only under a lock file created with O_EXCL
  * every change is an event: one new file in events/
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import getpass
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import yaml

from . import FRAMEWORK_VERSION
from .layout import Layout, guard_write

VIA_VALUES = {"genie", "notebook", "tool", "manual", "chat"}


# --------------------------------------------------------------------------- hashing and serialisation
def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def dump_json(obj) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def dump_yaml(obj) -> bytes:
    return yaml.safe_dump(obj, sort_keys=False, allow_unicode=True, width=120).encode("utf-8")


def load_any(path: str | Path):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".json":
        return json.loads(text)
    if p.suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    return text


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- identity
def current_user() -> str:
    """The account e-mail of this session (b2s.identity: notebook setup, Databricks SDK, or the OS user locally).
    Never typed by a person."""
    from .identity import account
    return account()["email"]


def current_via(default: str = "tool") -> str:
    v = os.environ.get("B2S_VIA", default)
    return v if v in VIA_VALUES else default


# --------------------------------------------------------------------------- writes
def atomic_write(path: str | Path, data: bytes) -> Path:
    """Write via a temporary file and rename, so a reader never sees half a file. Overwrites (for generated views)."""
    p = guard_write(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.tmp-{secrets.token_hex(4)}")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, p)
    return p


def write_once(path: str | Path, data: bytes) -> Path:
    """Write a file that must never be overwritten (versions, events, raw replies). Fails if it exists.
    Callers that allocate the name (versions) hold a lock, so the exists-check cannot race."""
    p = guard_write(path)
    if p.exists():
        raise FileExistsError(f"write-once file exists, refusing to overwrite: {p}")
    return atomic_write(p, data)


# --------------------------------------------------------------------------- locks
class LockTimeout(TimeoutError):
    pass


_CAPS: dict = {}


def lock_mode(layout: Layout) -> str:
    """o_excl (default) | mkdir — from project.yaml capabilities, written by `b2s doctor` after checks K-02/MKDIR."""
    p = layout.project_yaml
    try:
        m = p.stat().st_mtime
    except FileNotFoundError:
        return "o_excl"
    if _CAPS.get(str(p), (None,))[0] != m:
        cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        _CAPS[str(p)] = (m, (cfg.get("capabilities") or {}).get("lock_mode", "o_excl"))
    return _CAPS[str(p)][1]


@contextlib.contextmanager
def file_lock(layout: Layout, name: str, timeout: float = 30.0, stale_after: float = 120.0):
    """Exclusive lock on state/locks/<name>.lock: O_CREAT|O_EXCL (K-02), or os.mkdir when the doctor found that
    O_EXCL does not work on this file system. A lock older than `stale_after` seconds is broken (its holder crashed)."""
    if lock_mode(layout) == "mkdir":
        with _mkdir_lock(layout, name, timeout, stale_after):
            yield
        return
    lock = guard_write(layout.locks_dir / f"{name}.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps({"pid": os.getpid(), "user": current_user(), "at": time.time()}))
            break
        except (FileExistsError, PermissionError):
            # PermissionError: on Windows a lock file that another process is deleting cannot be created yet.
            try:
                if time.time() - lock.stat().st_mtime > stale_after:
                    lock.unlink(missing_ok=True)
                    continue
            except (FileNotFoundError, PermissionError):
                pass
            if time.monotonic() > deadline:
                raise LockTimeout(f"could not get lock {name} within {timeout}s")
            time.sleep(0.005 + secrets.randbelow(10) / 1000)
    try:
        yield
    finally:
        for _ in range(50):
            try:
                lock.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:          # Windows: briefly held open by an antivirus scan or another process
                time.sleep(0.01)


@contextlib.contextmanager
def _mkdir_lock(layout: Layout, name: str, timeout: float, stale_after: float):
    lock = guard_write(layout.locks_dir / f"{name}.lockdir")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.mkdir(lock)
            break
        except (FileExistsError, PermissionError):
            try:
                if time.time() - lock.stat().st_mtime > stale_after:
                    os.rmdir(lock)
                    continue
            except (FileNotFoundError, PermissionError, OSError):
                pass
            if time.monotonic() > deadline:
                raise LockTimeout(f"could not get lock {name} within {timeout}s")
            time.sleep(0.005 + secrets.randbelow(10) / 1000)
    try:
        yield
    finally:
        try:
            os.rmdir(lock)
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- sequential ids (DC-09)
def next_id(layout: Layout, prefix: str, width: int = 4) -> str:
    """Next sequential id for a prefix (E, Q, A, IN, GR, AR, APR, CR, IF, SN, H). Never reused."""
    counter = layout.ids_dir / f"{prefix}.next"
    with file_lock(layout, f"id-{prefix}"):
        n = int(counter.read_text(encoding="utf-8").strip()) if counter.exists() else 1
        atomic_write(counter, f"{n + 1}\n".encode())
    return f"{prefix}-{n:0{width}d}"


def stable_id(prefix: str, identity: dict | list | str, length: int = 6) -> str:
    """Stable hash id for items that code derives again on each run (DC-03): same identity -> same id."""
    raw = identity if isinstance(identity, str) else json.dumps(identity, sort_keys=True, default=str)
    return f"{prefix}-{hashlib.sha256(raw.encode()).hexdigest()[:length]}"


# --------------------------------------------------------------------------- events (design §7.2)
_LAST_NS = [0]


def emit_event(layout: Layout, action: str, *, app: str | None = None, step: str | None = None,
               items: list | None = None, outputs: dict | None = None, note: str | None = None,
               via: str | None = None, extra: dict | None = None) -> str:
    """Append one event as one new file. Events are never changed or deleted."""
    # Monotonic within a process even when the system clock is coarse (Windows), so events sort in write order.
    ns = max(time.time_ns(), _LAST_NS[0] + 1000)
    _LAST_NS[0] = ns
    t = _dt.datetime.fromtimestamp(ns / 1e9, _dt.timezone.utc)
    stamp = t.strftime("%Y%m%dT%H%M%S") + f"{(ns // 1000) % 1_000_000:06d}Z"
    eid = f"EV-{stamp}-{secrets.token_hex(2)}"
    ev = {
        "id": eid, "at": now_iso(), "user": current_user(), "via": via or current_via(),
        "notebook_run": os.environ.get("B2S_NOTEBOOK_RUN", "interactive" if (via or current_via()) == "notebook" else None),
        "framework_version": FRAMEWORK_VERSION, "app": app, "action": action, "step": step,
        "items": items or [], "outputs": outputs or {}, "note": note,
        "run_by": os.environ.get("B2S_RUN_BY"),          # genie | person, set by the notebook that ran
    }
    if extra:
        ev.update(extra)
    write_once(layout.events_dir / stamp[:8] / stamp[9:11] / f"{eid}.json", dump_json(ev))
    return eid


def list_events(layout: Layout, app: str | None = None, action: str | None = None) -> list[dict]:
    out = []
    if not layout.events_dir.exists():
        return out
    for f in sorted(layout.events_dir.rglob("EV-*.json")):
        ev = json.loads(f.read_text(encoding="utf-8"))
        if (app is None or ev.get("app") == app) and (action is None or ev.get("action") == action):
            out.append(ev)
    return out


# --------------------------------------------------------------------------- application lease (fallback for K-02)
class LeaseHeld(RuntimeError):
    pass


def acquire_lease(layout: Layout, app: str, hours: float = 2.0) -> dict:
    """One writer per application. Refuses while another user holds a valid lease; renews our own."""
    path = layout.state_dir_app(app) / "lease.json"
    with file_lock(layout, f"lease-{app}"):
        if path.exists():
            cur = json.loads(path.read_text(encoding="utf-8"))
            if cur["user"] != current_user() and cur["expires"] > time.time():
                raise LeaseHeld(f"{app} is leased by {cur['user']} until {time.ctime(cur['expires'])}")
        lease = {"user": current_user(), "since": now_iso(), "expires": time.time() + hours * 3600}
        atomic_write(path, dump_json(lease))
    return lease


def release_lease(layout: Layout, app: str) -> None:
    path = layout.state_dir_app(app) / "lease.json"
    with file_lock(layout, f"lease-{app}"):
        if path.exists() and json.loads(path.read_text(encoding="utf-8"))["user"] == current_user():
            guard_write(path).unlink()
