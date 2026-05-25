"""Replay guard for `/dao/submit_contribution` — mirrors Rails `duplicate_dao_submission_signature?`
(Rails.cache write-unless-exist keyed on SHA256 of the Request-Transaction-ID signature).

Backed by a small sqlite file so it survives restarts. With the `split`-gem gate keyed on
contributor, a given contributor's submissions always hit the same backend, so a Python-local
store dedups that cohort consistently. (If we ever need cross-backend dedup, point this at
Edgar's Redis instead.)
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading

_DB_PATH = os.environ.get("DAO_PROTOCOL_DEDUP_DB", "/home/ubuntu/dao_protocol/dedup.sqlite3")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.execute("CREATE TABLE IF NOT EXISTS seen (sig_hash TEXT PRIMARY KEY, ts INTEGER)")
        _conn.commit()
    return _conn


def is_duplicate(signature_base64: str) -> bool:
    """Record this signature; return True iff it was already present (a replay)."""
    if not (signature_base64 or "").strip():
        return False
    h = hashlib.sha256(signature_base64.encode("utf-8")).hexdigest()
    import time
    with _lock:
        conn = _connection()
        try:
            conn.execute("INSERT INTO seen (sig_hash, ts) VALUES (?, ?)", (h, int(time.time())))
            conn.commit()
            return False  # newly inserted → not a duplicate
        except sqlite3.IntegrityError:
            return True   # already present → duplicate
