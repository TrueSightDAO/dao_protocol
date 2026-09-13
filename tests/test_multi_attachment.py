"""Contract A (ordered pairing): the ``--attachment`` CLI flag is repeatable and
EdgarClient.submit() sends one ordered multipart ``attachment`` part per file.

Scope (PR1): CLI passthrough + multipart emission only. The server-side upload
loop that consumes the extra parts is PR2 -- until then the server reads the
first part, so these tests pin the *transport* contract, not the upload.
"""

from __future__ import annotations

import pytest

from truesight_dao_client.edgar_client import (
    EdgarClient,
    _DESTINATION_LABEL_RE,
    build_event_cli,
)


class _DummyResponse:
    status_code = 200
    ok = True

    def json(self):
        return {"status": "ok"}

    text = '{"status": "ok"}'


# --------------------------------------------------------------- submit() layer


def _client(monkeypatch):
    c = EdgarClient(
        email="garyjob@truesight.me",
        public_key_b64="PUB",
        private_key_b64="PRIV",
        base_url="http://test",
    )

    def _fake_sign(event_name, attributes):
        return {}, "txn", "SIGNED TEXT"

    monkeypatch.setattr(c, "sign", _fake_sign)
    captured = {}

    def _fake_post(url, files=None, timeout=None):
        captured["url"] = url
        captured["files"] = files
        return _DummyResponse()

    monkeypatch.setattr(c.session, "post", _fake_post)
    return c, captured


def test_submit_single_path_emits_one_part(monkeypatch, tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"AAA")
    c, cap = _client(monkeypatch)
    c.submit("ASSET RECEIPT EVENT", {"x": "y"}, attached_file_path=str(f))
    atts = cap["files"]["attachment"]
    assert isinstance(atts, list) and len(atts) == 1
    assert atts[0] == ("a.pdf", b"AAA")


def test_submit_list_emits_ordered_parts(monkeypatch, tmp_path):
    f1 = tmp_path / "pix.jpg"
    f2 = tmp_path / "fbn.jpg"
    f1.write_bytes(b"ONE")
    f2.write_bytes(b"TWO")
    c, cap = _client(monkeypatch)
    c.submit("ASSET RECEIPT EVENT", {"x": "y"}, attached_file_path=[str(f1), str(f2)])
    atts = cap["files"]["attachment"]
    # order is the contract: part k binds to the k-th destination URL
    assert [name for name, _ in atts] == ["pix.jpg", "fbn.jpg"]
    assert [data for _, data in atts] == [b"ONE", b"TWO"]


def test_submit_missing_file_raises(monkeypatch, tmp_path):
    c, _ = _client(monkeypatch)
    with pytest.raises(FileNotFoundError):
        c.submit(
            "ASSET RECEIPT EVENT",
            {"x": "y"},
            attached_file_path=[str(tmp_path / "nope.jpg")],
        )


# ------------------------------------------------------------------- CLI layer


DEST_LABEL = "Destination Asset Receipt File Location"
URL1 = "https://github.com/TrueSightDAO/.github/blob/main/assets/pix.jpg"
URL2 = "https://github.com/TrueSightDAO/.github/blob/main/assets/fbn.jpg"


def _make_main(monkeypatch, tmp_path):
    """A tiny 1-label event CLI that records the attrs + attachments handed to submit()."""
    seen = {}

    def _fake_from_env(cls):
        inst = EdgarClient(
            email="garyjob@truesight.me",
            public_key_b64="PUB",
            private_key_b64="PRIV",
            base_url="http://test",
        )
        return inst

    def _fake_submit(self, event_name, attributes, **kw):
        seen["event_name"] = event_name
        seen["attributes"] = list(attributes)
        seen["attached"] = kw.get("attached_file_path")
        return _DummyResponse()

    monkeypatch.setattr(EdgarClient, "from_env", classmethod(_fake_from_env))
    monkeypatch.setattr(EdgarClient, "submit", _fake_submit)
    main = build_event_cli(
        event_name="ASSET RECEIPT EVENT",
        canonical_labels=["Currency", "QR Code", DEST_LABEL],
    )
    return main, seen


def test_cli_two_files_two_destinations_ok(monkeypatch, tmp_path):
    main, seen = _make_main(monkeypatch, tmp_path)
    f1 = tmp_path / "pix.jpg"
    f2 = tmp_path / "fbn.jpg"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    DEST_LABEL_2 = (
        "Destination Fbn Receipt File Location"  # distinct label (labels dedupe)
    )
    rc = main(
        [
            "--currency",
            "PA",
            "--qr-code",
            "2024OSCAR_20260121_12",
            f"--{DEST_LABEL.lower().replace(' ', '-')}",
            URL1,
            "--attr",
            f"{DEST_LABEL_2}={URL2}",
            "--attachment",
            str(f1),
            "--attachment",
            str(f2),
        ]
    )
    assert rc == 0
    assert seen["attached"] == [str(f1), str(f2)]
    labels = [lbl for lbl, _ in seen["attributes"]]
    assert sum(1 for dest_lbl in labels if _DESTINATION_LABEL_RE.match(dest_lbl)) == 2


def test_cli_count_mismatch_errors(monkeypatch, tmp_path, capsys):
    main, seen = _make_main(monkeypatch, tmp_path)
    f1 = tmp_path / "pix.jpg"
    f2 = tmp_path / "fbn.jpg"
    f1.write_bytes(b"1")
    f2.write_bytes(b"2")
    with pytest.raises(SystemExit):
        main(
            [
                "--currency",
                "PA",
                f"--{DEST_LABEL.lower().replace(' ', '-')}",
                URL1,
                "--attachment",
                str(f1),
                "--attachment",
                str(f2),
            ]
        )
    assert "attached" not in seen  # parser.error fired before submit()


def test_cli_single_file_unchanged(monkeypatch, tmp_path):
    main, seen = _make_main(monkeypatch, tmp_path)
    f1 = tmp_path / "solo.pdf"
    f1.write_bytes(b"X")
    rc = main(["--currency", "PA", "--attachment", str(f1)])
    assert rc == 0
    # single-file still auto-fills Attached Filename + one Destination label
    assert seen["attached"] == [str(f1)]
    labels = [lbl for lbl, _ in seen["attributes"]]
    assert "Attached Filename" in labels
    assert sum(1 for dest_lbl in labels if _DESTINATION_LABEL_RE.match(dest_lbl)) == 1
