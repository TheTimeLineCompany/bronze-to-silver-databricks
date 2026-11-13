"""Who is working: taken from the Databricks account, never typed.

Order: environment (set by the notebook setup cell or a test) -> Databricks SDK (`current_user.me()`: e-mail and
display name) -> the operating-system user (local runs only). The result is cached in the environment, so tools
started from the same session (Genie's `python -m b2s ...`) see the same identity.

Genie Code runs with the worker's own permissions, so this is the worker's account. Approvals record it next to
the name the worker types as a signature (design §10; limit R-02: the account shows whose session it is).
"""
from __future__ import annotations

import getpass
import os


def account() -> dict:
    email, name = os.environ.get("B2S_USER"), os.environ.get("B2S_USER_NAME")
    source = "env" if email else None
    if not email:
        try:  # Databricks: the workspace account of this session
            from databricks.sdk import WorkspaceClient
            me = WorkspaceClient().current_user.me()
            email, name, source = me.user_name, me.display_name, "databricks"
            os.environ["B2S_USER"] = email
            if name:
                os.environ["B2S_USER_NAME"] = name
        except Exception:  # noqa: BLE001 - no SDK, no workspace: local run
            email, source = getpass.getuser(), "os"
    return {"email": email, "name": name or None, "source": source}


def from_workspace(spark=None) -> dict:
    """Notebook setup: current_user() from Spark, display name from the SDK when available."""
    if spark is not None and not os.environ.get("B2S_USER"):
        try:
            os.environ["B2S_USER"] = spark.sql("SELECT current_user() u").collect()[0]["u"]
        except Exception:  # noqa: BLE001
            pass
    if not os.environ.get("B2S_USER_NAME"):
        try:
            from databricks.sdk import WorkspaceClient
            name = WorkspaceClient().current_user.me().display_name
            if name:
                os.environ["B2S_USER_NAME"] = name
        except Exception:  # noqa: BLE001
            pass
    return account()


def label(acc: dict | None = None) -> str:
    """How the account appears in a statement: 'Jane Doe (jane.doe@client.com)' or the e-mail alone."""
    acc = acc or account()
    return f"{acc['name']} ({acc['email']})" if acc.get("name") else acc["email"]


def matches(text: str, acc: dict | None = None) -> bool:
    """True if the name in a statement is this account: its e-mail, its display name, or both."""
    acc = acc or account()
    t = " ".join(text.lower().split())
    return bool(acc["email"] and acc["email"].lower() in t) or bool(acc.get("name") and t == acc["name"].lower())
