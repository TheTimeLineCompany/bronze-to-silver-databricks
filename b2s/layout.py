"""All paths of a project folder, and the write guard.

Every write in the framework goes through `guard_write(path)` (called by b2s.store). Rules (DC-02, DB-06):
  * Test mode (env B2S_TEST=1 or pytest running): a write is allowed only under B2S_TEST_ROOT. If that is not set,
    every write fails. Tests can therefore never touch a live project folder.
  * Normal mode: a write is allowed only under a registered project root (the Layout that is in use).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

APP_ID = re.compile(r"^S[0-9]{2}_[a-z0-9_]+$")

_ALLOWED_ROOTS: set[Path] = set()


class WriteGuardError(RuntimeError):
    """A write outside the allowed root."""


def in_test_mode() -> bool:
    return os.environ.get("B2S_TEST") == "1" or "PYTEST_CURRENT_TEST" in os.environ


def _norm(path: str | Path) -> Path:
    """Absolute, normalised path without resolving the file itself (resolve() on Windows can return a \\\\?\\ form
    for a file that is being deleted). '..' parts are collapsed, so they cannot escape the root."""
    return Path(os.path.normcase(os.path.abspath(str(path))))


def guard_write(path: str | Path) -> Path:
    p = _norm(path)
    if in_test_mode():
        root = os.environ.get("B2S_TEST_ROOT")
        if not root:
            raise WriteGuardError(f"test mode without B2S_TEST_ROOT: refused write to {p}")
        if not _under(p, _norm(root)):
            raise WriteGuardError(f"test mode: refused write outside B2S_TEST_ROOT ({root}): {p}")
        return Path(os.path.abspath(str(path)))
    if not any(_under(p, _norm(r)) for r in _ALLOWED_ROOTS):
        raise WriteGuardError(f"refused write outside the project folder: {p}")
    return Path(os.path.abspath(str(path)))


def _under(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


# V1.3 phase folder of each output (work/<phase>/<stem>). The phase sequence stays as in V1.3:
# P1 register + bronze baseline, P2 documents + application understanding + scope, P3 central (logical) model, P4 STTM.
PHASE_OF = [
    ("baseline/", "P1"),
    ("documents/", "P2"), ("understanding/", "P2"), ("research/", "P2"), ("columns/", "P2"), ("scope/", "P2"),
    ("models/dependencies", "P2"), ("models/process", "P2"), ("models/conceptual", "P2"),
    ("models/logical", "P3"),
    ("sttm/", "P4"), ("models/mapping", "P4"),
    ("build/", "P5"), ("qa/", "P5"),
    ("release/", "P6"),
]


def phase_of(stem: str) -> str:
    for prefix, phase in PHASE_OF:
        if stem.startswith(prefix):
            return phase
    raise ValueError(f"no phase folder for {stem!r}; add it to layout.PHASE_OF")


class Layout:
    """Paths of one project folder (design §17.2). Builds every path; nothing else joins paths by hand."""

    def __init__(self, project_root: str | Path):
        self.root = Path(os.path.abspath(str(project_root)))
        _ALLOWED_ROOTS.add(self.root)

    # ---- project level
    @property
    def project_yaml(self) -> Path:
        return self.root / "project.yaml"

    @property
    def ontology_dir(self) -> Path:
        return self.root / "_project"

    @property
    def events_dir(self) -> Path:
        return self.root / "events"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def ids_dir(self) -> Path:
        return self.state_dir / "ids"

    @property
    def locks_dir(self) -> Path:
        return self.state_dir / "locks"

    @property
    def plugins_dir(self) -> Path:
        return self.root / "plugins"

    @property
    def contrib_dir(self) -> Path:
        return self.root / "contrib"

    # ---- application level
    def app_dir(self, app: str) -> Path:
        if not APP_ID.match(app):
            raise ValueError(f"application id must look like S01_name: {app!r}")
        return self.root / "apps" / app

    def app_yaml(self, app: str) -> Path:
        return self.app_dir(app) / "app.yaml"

    def apps(self) -> list[str]:
        d = self.root / "apps"
        return sorted(p.name for p in d.iterdir() if p.is_dir() and APP_ID.match(p.name)) if d.exists() else []

    def sub(self, app: str, *parts: str) -> Path:
        """apps/<app>/<parts...>"""
        return self.app_dir(app).joinpath(*parts)

    def stem(self, app: str, stem: str) -> Path:
        """Path of a versioned file without its .vNNN.ext part, e.g. stem(app, 'models/logical').
        The short stem is the identifier; the file lives in the V1.3 phase folder work/<phase>/ (PHASE_OF)."""
        return self.app_dir(app) / "work" / phase_of(stem) / stem

    def review_dir(self, app: str) -> Path:
        """Approval requests and their one-page views (V1.3 review/ folder)."""
        return self.app_dir(app) / "review" / "approvals"

    def state_dir_app(self, app: str) -> Path:
        """Items and the application lease (V1.3 state/ folder)."""
        return self.app_dir(app) / "state"

    def rel(self, path: str | Path) -> str:
        return Path(os.path.relpath(os.path.abspath(str(path)), str(self.root))).as_posix()

    def contains(self, path: str | Path) -> bool:
        return _under(_norm(path), _norm(self.root))
