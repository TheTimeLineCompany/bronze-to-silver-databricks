"""Functions run in child processes by the concurrency tests (must be importable at module level)."""


def alloc_ids(root: str, n: int) -> list:
    from b2s.layout import Layout
    from b2s.store import next_id
    layout = Layout(root)
    return [next_id(layout, "E") for _ in range(n)]


def save_versions(root: str, worker: int, n: int) -> list:
    from b2s.layout import Layout
    from b2s import versions
    layout = Layout(root)
    out = []
    for i in range(n):
        v = versions.save(layout, layout.root / "apps" / "S01_x" / "models" / "m", "json",
                          {"worker": worker, "i": i}, reason="test")
        out.append(v.n)
    return out
