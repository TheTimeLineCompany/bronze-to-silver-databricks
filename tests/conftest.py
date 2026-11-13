import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _test_root(tmp_path, monkeypatch):
    """Every test writes only under its own tmp_path (DC-02 write guard)."""
    monkeypatch.setenv("B2S_TEST", "1")
    monkeypatch.setenv("B2S_TEST_ROOT", str(tmp_path))
    monkeypatch.setenv("B2S_USER", "worker@example.com")
    monkeypatch.delenv("B2S_VIA", raising=False)
    yield


@pytest.fixture
def project(tmp_path):
    from b2s.project import init_project
    return init_project(tmp_path / "proj", "Test project")
