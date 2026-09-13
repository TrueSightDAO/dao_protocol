"""Contract A (ordered pairing), server half (PR2).

- `github_upload.upload_all_if_referenced()` uploads attachment k to destination
  URL k, in order.
- The `/dao/submit_contribution` route reads repeated `attachment` parts and
  routes a single part through the unchanged single-file path.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from truesight_dao_client.server import dispatch
from truesight_dao_client.server.crypto import verify
from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.services import github_upload
from truesight_dao_client.server.sheets import telegram_raw_log

client = TestClient(create_app())


def _settings_pat(pat: str = "PAT"):
    return SimpleNamespace(github_pat=pat)


@pytest.fixture(autouse=True)
def _stub(monkeypatch):
    monkeypatch.setattr(telegram_raw_log, "add_record", lambda *a, **k: True)
    monkeypatch.setattr(dispatch, "dispatch_event", lambda text: None)
    monkeypatch.setattr(verify, "verify", lambda t: {"success": True, "message": "ok"})


# ------------------------------------------------- upload_all_if_referenced()


def test_ordered_pairing_uploads_k_to_kth_url(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    monkeypatch.setattr(
        github_upload.requests, "get", lambda *a, **k: SimpleNamespace(status_code=404)
    )
    seen = []
    monkeypatch.setattr(
        github_upload.requests,
        "put",
        lambda url, **k: seen.append(url) or SimpleNamespace(status_code=201),
    )
    text = (
        "Destination A: https://github.com/TrueSightDAO/.github/blob/main/assets/pix.jpg\n"
        "Destination B: https://github.com/TrueSightDAO/.github/blob/main/assets/fbn.jpg"
    )
    files = [("pix.jpg", b"ONE"), ("fbn.jpg", b"TWO")]
    assert github_upload.upload_all_if_referenced(text, files) is True
    assert seen[0].endswith("/contents/assets/pix.jpg")
    assert seen[1].endswith("/contents/assets/fbn.jpg")


def test_single_file_single_url_back_compat(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    monkeypatch.setattr(
        github_upload.requests, "get", lambda *a, **k: SimpleNamespace(status_code=404)
    )
    seen = []
    monkeypatch.setattr(
        github_upload.requests,
        "put",
        lambda url, **k: seen.append(url) or SimpleNamespace(status_code=201),
    )
    text = "x https://github.com/TrueSightDAO/.github/blob/main/assets/only.pdf"
    assert github_upload.upload_all_if_referenced(text, [("only.pdf", b"B")]) is True
    assert seen == [
        "https://api.github.com/repos/TrueSightDAO/.github/contents/assets/only.pdf"
    ]


def test_more_files_than_urls_fails(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    monkeypatch.setattr(
        github_upload.requests, "get", lambda *a, **k: SimpleNamespace(status_code=404)
    )
    monkeypatch.setattr(
        github_upload.requests, "put", lambda *a, **k: SimpleNamespace(status_code=201)
    )
    text = "only one https://github.com/TrueSightDAO/.github/blob/main/assets/one.pdf"
    assert (
        github_upload.upload_all_if_referenced(text, [("a", b"1"), ("b", b"2")])
        is False
    )


def test_no_url_or_pat_is_false(monkeypatch):
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat())
    assert github_upload.upload_all_if_referenced("no url", [("a", b"1")]) is False
    monkeypatch.setattr(github_upload, "get_settings", lambda: _settings_pat(""))
    assert (
        github_upload.upload_all_if_referenced(
            "https://github.com/o/r/blob/main/p", [("a", b"1")]
        )
        is False
    )


# ---------------------------------------------------- /dao route wiring


def test_route_single_attachment_unchanged(monkeypatch):
    monkeypatch.setattr(
        github_upload, "upload_if_referenced", lambda text, b, fn=None: True
    )
    r = client.post(
        "/dao/submit_contribution",
        data={
            "text": "see https://github.com/TrueSightDAO/.github/blob/main/assets/x.pdf"
        },
        files={"attachment": ("x.pdf", b"bytes", "application/pdf")},
    )
    assert r.status_code == 200
    assert r.json()["fileUploadedToGithub"] is True


def test_route_multi_attachment_uses_ordered_uploader(monkeypatch):
    monkeypatch.setattr(
        github_upload,
        "upload_if_referenced",
        lambda *a, **k: pytest.fail("single-file path must not run for 2 parts"),
    )
    captured = {}

    def _fake_all(text, files):
        captured["files"] = files
        return True

    monkeypatch.setattr(github_upload, "upload_all_if_referenced", _fake_all)
    r = client.post(
        "/dao/submit_contribution",
        data={
            "text": (
                "a https://github.com/TrueSightDAO/.github/blob/main/assets/a.jpg "
                "b https://github.com/TrueSightDAO/.github/blob/main/assets/b.jpg"
            )
        },
        files=[
            ("attachment", ("a.jpg", b"1", "image/jpeg")),
            ("attachment", ("b.jpg", b"2", "image/jpeg")),
        ],
    )
    assert r.status_code == 200
    assert r.json()["fileUploadedToGithub"] is True
    assert [name for name, _ in captured["files"]] == ["a.jpg", "b.jpg"]


def test_route_no_attachment(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        github_upload,
        "upload_if_referenced",
        lambda *a, **k: called.update(n=called["n"] + 1) or True,
    )
    r = client.post("/dao/submit_contribution", data={"text": "no file here"})
    assert r.status_code == 200
    assert r.json()["fileUploadedToGithub"] is False
    assert called["n"] == 0
