"""PR4c(a): ping_sophia can name a handoff plan for Sophia's auto-claim.

The plan_file must travel *inside* the signed canonical payload so Sophia's
verify_payload accepts it and the autopilot (single writer of
active_supervision.json) can record the claim.
"""

from __future__ import annotations

from truesight_dao_client.modules import ping_sophia


class _Resp:
    status_code = 200
    ok = True
    text = "{}"

    def json(self):
        return {"response": "ok"}


def _run(monkeypatch, **kw):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002 (mirror requests' kwarg)
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json
        return _Resp()

    monkeypatch.setattr(ping_sophia.requests, "post", fake_post)
    monkeypatch.setattr(ping_sophia, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("PUBLIC_KEY", "pub")
    monkeypatch.setenv("PRIVATE_KEY", "priv")
    monkeypatch.setattr(ping_sophia, "load_private_key", lambda k: object())
    monkeypatch.setattr(ping_sophia, "sign_payload", lambda key, canon: "sig:" + canon)
    ping_sophia.ping(
        "hello", session_id="s1", url="http://x/chat-blocking", timeout=5, **kw
    )
    return captured


def test_plan_file_is_inside_signed_payload(monkeypatch):
    cap = _run(monkeypatch, plan_file="plans/FOO.md")
    payload = cap["body"]["payload"]
    assert payload["plan_file"] == "plans/FOO.md"
    # signature is computed over the canonical payload, so plan_file must appear in it
    assert "plans/FOO.md" in cap["body"]["signature"]


def test_plan_file_omitted_when_not_given(monkeypatch):
    cap = _run(monkeypatch)
    assert "plan_file" not in cap["body"]["payload"]
