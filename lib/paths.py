"""Where the runtime library finds the project registries (key rules, shared masters, survivorship).

V1.4: registries live in the project folder (<project>/_project/). Generated notebooks set B2S_REGISTRY_DIR or pass
`root=<project folder>`. The framework's registry_template/ is the last fallback (examples only).
"""
from __future__ import annotations

import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def registry_file(name: str, root: str | None = None) -> str:
    env = os.environ.get("B2S_REGISTRY_DIR")
    cands = [env] if env else []
    if root:
        cands += [os.path.join(root, "_project"), os.path.join(root, "registry"), root]
    cands += [os.path.join(_ROOT, "registry"), os.path.join(_ROOT, "registry_template")]
    for d in cands:
        if d and os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    return os.path.join(cands[0] if cands else _ROOT, name)
