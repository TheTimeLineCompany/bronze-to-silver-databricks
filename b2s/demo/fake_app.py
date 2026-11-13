"""Fake application S90_yardops (container yard logistics): bronze CSVs + inbox documents.

Layout written by make_fake_app(out_dir):
  out_dir/bronze/schema.json            {"tables": {"yard.cntr_mst": {"columns": [[name, type], ...], "view": null}, ...}}
  out_dir/bronze/<schema>/<table>.csv   data (empty string = NULL)
  out_dir/inbox/...                     documents for P3

The data contains the cases the tests need: single and composite keys, a near key (two exact duplicate rows),
a key that needs 5 columns (no key within max_key_size=4), a table with no key at all, an exact copy (backup),
an empty table, an application-log table, a personal-data table, audit and CDC columns, a *_nm-only table, a view.
All names, emails, phones and addresses are fictional.
"""
from __future__ import annotations

import csv
import itertools
import json
import random
from pathlib import Path

APP = "S90_yardops"
SCHEMAS = ["yard"]
LOOKUP_SCHEMAS = ["yardlkp"]

CONTACTS = [
    ("C001", "Anna Berg", "anna.berg@carrier-one.example", "+49 170 5551234"),
    ("C002", "Jonas Keller", "jonas.keller@carrier-one.example", "+49 171 5554321"),
    ("C003", "Mira Novak", "mira.novak@shipline.example", "+420 601 555 777"),
    ("C004", "Lars Olsen", "lars.olsen@shipline.example", "+45 20 55 66 77"),
    ("C005", "Sara Lind", "sara.lind@portops.example", "+46 70 555 1122"),
    ("C006", "Tom Brandt", "tom.brandt@portops.example", "+49 152 5559876"),
]
IPS = ["10.12.3.45", "10.12.3.46", "192.168.40.7", "172.16.5.21"]
AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 Safari/605.1.15"]
AUDIT_USERS = ["jdoe_ops", "mkrause_ops", "batch_loader"]


def install(layout, fake: dict, register: bool = True) -> None:
    """Register S90_yardops in a project and copy the inbox keeping sub-folders (project.copy_into_inbox flattens)."""
    from ..project import register_app
    from ..store import atomic_write, emit_event
    if register:
        register_app(layout, APP, "YardOps (fake)", SCHEMAS, LOOKUP_SCHEMAS,
                     bronze={"connector": "local_csv", "root": fake["bronze_root"]},
                     description="Fictional container yard application for demos and tests.")
    root = Path(fake["inbox_root"])
    for f in fake["inbox"]:
        rel = Path(f).relative_to(root)
        atomic_write(layout.sub(APP, "inbox", *rel.parts), Path(f).read_bytes())
    emit_event(layout, "inbox_files_added", app=APP, step="P2.1", note=f"{len(fake['inbox'])} demo files")


def sensitive_values() -> list[str]:
    """Raw values that must never appear in any file the framework writes."""
    vals = [c[1] for c in CONTACTS] + [c[2] for c in CONTACTS] + [c[3] for c in CONTACTS] + IPS + AGENTS
    return vals + [u for u in AUDIT_USERS if u != "batch_loader"]


def _write_csv(path: Path, cols: list, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in cols])
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def make_fake_app(out_dir: str | Path) -> dict:
    rnd = random.Random(20261113)
    out = Path(out_dir)
    bronze = out / "bronze"
    tables: dict = {}

    def table(name, cols, rows, view=None):
        tables[name] = {"columns": cols, "view": view}
        schema, t = name.split(".")
        if view is None:                                    # a view has no data file; the reader projects its base
            _write_csv(bronze / schema / f"{t}.csv", cols, rows)

    # container master: single key cntr_no; created_at unique (audit -> must not become the key)
    cntr = [f"MSCU{1000000 + i * 7:07d}" for i in range(60)]
    table("yard.cntr_mst",
          [["cntr_no", "string"], ["iso_type", "string"], ["owner_cd", "string"], ["created_by", "string"],
           ["created_at", "timestamp"]],
          [[c, rnd.choice(["22G1", "45G1", "22R1"]), rnd.choice(["MSC", "MAE", "CMA"]), rnd.choice(AUDIT_USERS),
            f"2026-01-{1 + i % 28:02d} 08:{i % 60:02d}:{i % 59:02d}"] for i, c in enumerate(cntr)])

    # move plan: plan_id is a near key (two exact duplicate rows)
    plans = [[f"P{i:04d}", rnd.choice(["NEW", "APPR", "DONE"]), f"2026-02-{1 + i % 28:02d} 10:00:{i % 60:02d}"]
             for i in range(1, 41)]
    table("yard.mv_plan", [["plan_id", "string"], ["plan_status", "string"], ["created_at", "timestamp"]],
          plans + [list(plans[2]), list(plans[6])])

    # move legs: composite key plan_id + leg_no; load_version (CDC) is unique per row and must not become the key
    legs, lv = [], 0
    locs = ["BLK-A", "BLK-B", "BLK-C", "GATE-1", "QUAY-2"]
    for i in range(1, 41):
        for leg in (1, 2):
            lv += 1
            legs.append([f"P{i:04d}", leg, rnd.choice(cntr), rnd.choice(locs), rnd.choice(locs),
                         f"2026-03-{1 + rnd.randrange(10):02d}", lv])
    leg_cols = [["plan_id", "string"], ["leg_no", "int"], ["cntr_no", "string"], ["from_loc", "string"],
                ["to_loc", "string"], ["moved_at", "date"], ["load_version", "int"]]
    table("yard.mv_leg", leg_cols, legs)
    table("yard.mv_leg_bkp", leg_cols, [list(r) for r in legs])          # exact copy

    # locations: key loc_cd; loc_name is description-like (removed from the key search)
    table("yard.loc", [["loc_cd", "string"], ["loc_name", "string"]],
          [[c, f"Yard location {c}"] for c in locs])

    # berths: no code column, so *_nm is allowed into the key search (DC-10)
    table("yard.berth", [["berth_nm", "string"], ["berth_len_m", "double"]],
          [[f"North quay {i}", 250.0 + i * 10.5] for i in range(1, 9)])

    # rate card: the key needs all 5 code columns (no key within max_key_size=4)
    combos = list(itertools.product(["EU", "AS"], ["CAR1", "CAR2"], ["22G1", "45G1"], ["STD", "EXP"], ["SUM", "WIN"]))
    table("yard.rate_card",
          [["region_cd", "string"], ["carrier_cd", "string"], ["iso_type", "string"], ["svc_level", "string"],
           ["season_cd", "string"], ["rate_eur", "double"]],
          [list(c) + [round(100 + rnd.random() * 50, 2)] for c in combos])

    # yard statistics: repeated rows, no key at all
    stat = [["2026-03-01", "BLK-A", 12], ["2026-03-01", "BLK-B", 9], ["2026-03-02", "BLK-A", 14]]
    table("yard.yard_stat", [["stat_day", "date"], ["block_cd", "string"], ["moves", "int"]],
          [list(stat[i % 3]) for i in range(30)])

    # application log: session id, IP, user agent, login time
    table("yard.usr_session",
          [["session_id", "string"], ["user_ip", "string"], ["user_agent", "string"], ["login_ts", "timestamp"]],
          [[f"{rnd.getrandbits(128):032x}", rnd.choice(IPS), rnd.choice(AGENTS),
            f"2026-03-0{1 + i % 9} 07:{i % 60:02d}:00"] for i in range(25)])

    # personal data
    table("yard.contact", [["contact_id", "string"], ["contact_name", "string"], ["email", "string"], ["phone", "string"]],
          [list(c) for c in CONTACTS])

    table("yard.empty_tbl", [["x_id", "string"], ["x_val", "string"]], [])

    # a plain view over cntr_mst
    table("yard.v_cntr", [["cntr_no", "string"], ["iso_type", "string"]], [], view={"text": "SELECT cntr_no, iso_type FROM yard.cntr_mst",
                                             "base_tables": ["yard.cntr_mst"], "columns": ["cntr_no", "iso_type"]})

    # lookup schema
    table("yardlkp.cntr_status", [["status_cd", "string"], ["status_desc", "string"]],
          [["NEW", "Created"], ["APPR", "Approved"], ["DONE", "Completed"]])

    bronze.mkdir(parents=True, exist_ok=True)
    (bronze / "schema.json").write_text(json.dumps({"tables": tables}, indent=2), encoding="utf-8")

    inbox = _write_inbox(out / "inbox")
    return {"app": APP, "schemas": SCHEMAS, "lookup_schemas": LOOKUP_SCHEMAS, "bronze_root": str(bronze),
            "inbox": [str(p) for p in inbox], "inbox_root": str(out / "inbox"), "sensitive_values": sensitive_values()}


OVERVIEW = """# YardOps — system overview

## Purpose
YardOps plans and records container moves inside the container yard.
Contact for questions: ops.lead@yardops.example, phone +49 40 555 0100.

## Workflow
1. A planner creates a move plan (table mv_plan).
2. The shift lead approves the plan.
3. Straddle carriers execute the legs of the plan (table mv_leg), one leg per hop.

## Interfaces
- MARS sends the container master and the vessel schedule.
- The terminal operating system receives move instructions.
"""

DICTIONARY = """# Data dictionary

## cntr_mst
- cntr_no: container number (ISO 6346)
- iso_type: ISO size/type code

## mv_plan
- plan_id: move plan id
- plan_status: NEW, APPR, DONE

## mv_leg
- plan_id, leg_no: one leg of a plan
- cntr_no: container moved
"""

SLIDES_OLD = """# YardOps training (old, v1)

## Slide 1: Welcome
## Slide 2: Planning screen
"""

NOTES_NEW = """# Workshop minutes 2026-02-10

## Attendees
## Decisions
- Legs are numbered from 1 per plan.
"""

NOTES_OLD = """# Workshop minutes 2025-11-02

## Attendees
## Open points
"""

# smallest valid PNG (1x1 pixel)
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000000"
                    "0200015e2d2a4d0000000049454e44ae426082")


def _write_inbox(d: Path) -> list[Path]:
    files = {
        "overview.md": OVERVIEW,
        "overview (copy).md": OVERVIEW,
        "data_dictionary.md": DICTIONARY,
        "slides_old_v1.md": SLIDES_OLD,
        "notes.md": NOTES_NEW,
        "archive/notes.md": NOTES_OLD,
    }
    out = []
    for name, text in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        out.append(p)
    p = d / "yard_layout.png"
    p.write_bytes(PNG)
    out.append(p)
    return out
