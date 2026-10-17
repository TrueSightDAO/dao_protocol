"""Tests for POST /dao/read_watermark_gps (A1.1). Reader mocked — no tesseract/network."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from truesight_dao_client.server.main import create_app
from truesight_dao_client.server.routes import watermark

client = TestClient(create_app())

_PHOTO = {"attachment": ("p.jpg", b"\xff\xd8\xff\xe0fake-jpeg-bytes", "image/jpeg")}


def _reader(**fields):
    return lambda path, **kwargs: fields


def test_missing_attachment_is_400():
    r = client.post("/dao/read_watermark_gps")
    assert r.status_code == 400
    assert r.json()["error"] == "missing_attachment"


def test_empty_attachment_is_400():
    r = client.post(
        "/dao/read_watermark_gps", files={"attachment": ("p.jpg", b"", "image/jpeg")}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "empty_attachment"


def test_south_west_is_negative_and_source_stamped(monkeypatch):
    monkeypatch.setattr(
        watermark.tw,
        "read_timemark_watermark",
        _reader(
            lat="3.522716",
            lat_ref="S",
            lon="52.094956",
            lon_ref="W",
            code="ABC123DEF456GH",
            method="tesseract",
        ),
    )
    r = client.post("/dao/read_watermark_gps", files=_PHOTO)
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "ok"
    assert body["lat"] == -3.522716
    assert body["lon"] == -52.094956
    assert body["source"] == "watermark"
    assert body["method"] == "tesseract"
    assert body["code"] == "ABC123DEF456GH"


def test_north_east_is_positive(monkeypatch):
    monkeypatch.setattr(
        watermark.tw,
        "read_timemark_watermark",
        _reader(lat="10.5", lat_ref="N", lon="20.25", lon_ref="E", method="vision"),
    )
    body = client.post("/dao/read_watermark_gps", files=_PHOTO).json()
    assert body["lat"] == 10.5
    assert body["lon"] == 20.25
    assert body["source"] == "watermark"


def test_missing_watermark_is_no_watermark(monkeypatch):
    monkeypatch.setattr(watermark.tw, "read_timemark_watermark", _reader())
    body = client.post("/dao/read_watermark_gps", files=_PHOTO).json()
    assert body["status"] == "no_watermark"
    assert body["lat"] is None and body["source"] is None


def test_missing_hemisphere_is_not_a_coordinate(monkeypatch):
    # A value without a hemisphere letter must NOT be coerced into a coordinate.
    monkeypatch.setattr(
        watermark.tw,
        "read_timemark_watermark",
        _reader(lat="3.522716", lat_ref="", lon="52.094956", lon_ref="W"),
    )
    body = client.post("/dao/read_watermark_gps", files=_PHOTO).json()
    assert body["status"] == "no_watermark"
    assert body["lat"] is None


def test_reader_exception_is_swallowed_200(monkeypatch):
    def boom(path, **kwargs):
        raise RuntimeError("crop failed")

    monkeypatch.setattr(watermark.tw, "read_timemark_watermark", boom)
    r = client.post("/dao/read_watermark_gps", files=_PHOTO)
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert r.json()["lat"] is None


def test_slow_read_times_out_and_returns_nulls(monkeypatch):
    def slow(path, **kwargs):
        time.sleep(1.0)
        return {"lat": "1.0", "lat_ref": "S", "lon": "2.0", "lon_ref": "W"}

    monkeypatch.setattr(watermark.tw, "read_timemark_watermark", slow)
    monkeypatch.setattr(
        watermark,
        "get_settings",
        lambda: type(
            "S",
            (),
            {"read_watermark_timeout_s": 0.05, "read_watermark_max_bytes": 12_000_000},
        )(),
    )
    body = client.post("/dao/read_watermark_gps", files=_PHOTO).json()
    assert body["status"] == "timeout"
    assert body["lat"] is None and body["lon"] is None


def test_oversize_upload_is_413(monkeypatch):
    monkeypatch.setattr(
        watermark,
        "get_settings",
        lambda: type(
            "S", (), {"read_watermark_timeout_s": 10, "read_watermark_max_bytes": 8}
        )(),
    )
    r = client.post("/dao/read_watermark_gps", files=_PHOTO)
    assert r.status_code == 413
    assert r.json()["error"] == "payload_too_large"


def test_ocr_only_by_default_passes_noop_vision(monkeypatch):
    seen = {}

    def capture(path, vision_fn=None, ocr_fn=None):
        seen["vision_fn"] = vision_fn
        return {}

    monkeypatch.setattr(watermark.tw, "read_timemark_watermark", capture)
    client.post("/dao/read_watermark_gps", files=_PHOTO)
    assert callable(seen["vision_fn"])
    assert seen["vision_fn"]({}) == ""  # opt-in gate: default path never hits Gemini
