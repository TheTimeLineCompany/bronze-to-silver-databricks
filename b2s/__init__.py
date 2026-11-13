"""Bronze-to-Silver framework V1.4 (team 1: bronze + documents -> approved STTM).

Design: docs/V1_4_DESIGN.md. All state lives in files of a project folder; see b2s.store and b2s.versions.
"""
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent
try:
    FRAMEWORK_VERSION = (FRAMEWORK_ROOT / "FRAMEWORK_VERSION").read_text(encoding="utf-8").strip()
except OSError:  # pragma: no cover
    FRAMEWORK_VERSION = "unknown"
