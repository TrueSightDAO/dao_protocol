#!/usr/bin/env python3
"""Ping Sophia (the TrueSight DAO autopilot) with a governor-signed message.

The reusable trigger for the **local-LLM → Sophia execution handoff**: after a
governor and a local LLM craft an implementation plan + execution roadmap and
commit the roadmap to ``agentic_ai_context``, any LLM/CLI on the governor's
machine can call this to hand the baton to Sophia — e.g. tell her to open a
Telegram topic, load the plan, and post a kickoff so the governor can step into
Telegram and monitor execution with her.

It signs a one-shot request the exact way Sophia's ``/chat-blocking`` endpoint
expects (RSA-PKCS1v15 / SHA-256 over the canonical JSON payload) and POSTs it
with the ``X-Public-Key`` header. **Access is governor-only — enforced by
Sophia**, not here: ``verify_payload`` rejects any public key not in the DAO
governor registry with HTTP 403. This module merely signs with whatever
identity is in ``./.env`` (EMAIL / PUBLIC_KEY / PRIVATE_KEY); a non-governor
key simply gets a 403 back.

Requires ``./.env`` with PUBLIC_KEY / PRIVATE_KEY (``truesight-dao-auth login``).

Run::

    python -m truesight_dao_client.modules.ping_sophia --message "..."
    python -m truesight_dao_client.modules.ping_sophia \\
        --message "Open a Telegram topic 'Exec: warm-up v2' and post a kickoff: \\
                   you've taken over execution of WARMUP_AUTOSEND_PLAN.md; read \\
                   its resume tracker and start at RESUME HERE." \\
        --session-id handoff-warmup-v2

    python -m truesight_dao_client.modules.ping_sophia \
        --message "Resume the board sprint plan at RESUME HERE." \
        --session-id handoff-sprint-board \
        --plan-file "plans/SPRINT_TRUESIGHT_ME_BOARD_PROPOSAL.md"
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from ..edgar_client import load_private_key, sign_payload

DEFAULT_SOPHIA_URL = "https://sophia.truesight.me/chat-blocking"


def _canonical(payload: dict) -> str:
    """Match app/auth.py verify_payload: compact, key-order preserved, unicode kept."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def ping(
    message: str,
    *,
    session_id: str | None,
    url: str,
    timeout: float,
    plan_file: str | None = None,
) -> dict:
    load_dotenv(Path.cwd() / ".env")
    pub = os.getenv("PUBLIC_KEY", "").strip()
    priv = os.getenv("PRIVATE_KEY", "").strip()
    if not pub or not priv:
        raise SystemExit(
            "Missing PUBLIC_KEY / PRIVATE_KEY in ./.env (run truesight-dao-auth login)."
        )

    payload = {
        "message": message,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": str(uuid.uuid4()),
    }
    # PR4c(a): optionally name the handoff plan so Sophia (the single writer of
    # agentic_ai_context/handoffs/active_supervision.json) records an
    # active-supervision claim for it. Included BEFORE signing so it travels
    # inside the signed canonical payload and passes verify_payload.
    if plan_file:
        payload["plan_file"] = plan_file
    signature = sign_payload(load_private_key(priv), _canonical(payload))

    headers = {"X-Public-Key": pub, "Content-Type": "application/json"}
    if session_id:
        headers["X-Session-Id"] = session_id
    resp = requests.post(
        url,
        headers=headers,
        json={"payload": payload, "signature": signature},
        timeout=timeout,
    )
    if resp.status_code == 403:
        raise SystemExit(
            "403 from Sophia — this key is not a registered governor. "
            "ping_sophia is governor-only."
        )
    if not resp.ok:
        raise SystemExit(f"Sophia returned HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        return resp.json()
    except ValueError:
        return {"response": resp.text}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Ping Sophia (autopilot) with a governor-signed message."
    )
    p.add_argument(
        "--message", required=True, help="The instruction / message to send Sophia."
    )
    p.add_argument(
        "--session-id",
        default=None,
        help="Optional X-Session-Id (groups a multi-turn handoff conversation).",
    )
    p.add_argument(
        "--url",
        default=os.getenv("SOPHIA_CHAT_URL", DEFAULT_SOPHIA_URL),
        help=f"Sophia /chat-blocking URL (default {DEFAULT_SOPHIA_URL} or $SOPHIA_CHAT_URL).",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="HTTP timeout seconds (Sophia may run tools).",
    )
    p.add_argument(
        "--plan-file",
        default=None,
        help="Optional handoff plan path (e.g. plans/FOO.md). Named in the signed "
        "payload so Sophia records an active-supervision claim (PR4c(a)).",
    )
    args = p.parse_args(argv)

    out = ping(
        args.message,
        session_id=args.session_id,
        url=args.url,
        timeout=args.timeout,
        plan_file=args.plan_file,
    )
    print(out.get("response") or out.get("message") or json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
