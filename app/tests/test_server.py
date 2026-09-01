# -*- coding: utf-8 -*-
import os

from fastapi.testclient import TestClient
from core import storage

import server as server_mod


def client():
    return TestClient(server_mod.server)


def test_health_and_dimensions():
    c = client()
    assert c.get("/api/health").json()["ok"] is True
    dims = c.get("/api/dimensions").json()
    assert len(dims) == 10
    local = [d for d in dims if not d["needs_vision"]]
    assert {d["dim_id"] for d in local} == {"D03", "D04"}


def test_upload_rejects_invalid_mp4(tmp_path):
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"\x00" * 1024)
    r = client().post("/api/upload", files={"file": ("fake.mp4", fake.read_bytes(),
                                                      "video/mp4")})
    assert r.status_code == 400
    assert "无效" in r.json()["detail"] or "无法读取" in r.json()["detail"]


def test_upload_rejects_oversized_stream(tmp_path, monkeypatch):
    fake = tmp_path / "large.mp4"
    fake.write_bytes(b"\x00" * 1024)
    monkeypatch.setattr(server_mod, "MAX_UPLOAD_BYTES", 1)
    r = client().post("/api/upload", files={"file": ("large.mp4", fake.read_bytes(),
                                                      "video/mp4")})
    assert r.status_code == 413


def test_video_file_rejects_path_traversal(tmp_env):
    secret = tmp_env / "secret.mp4"
    secret.write_bytes(b"SECRET")
    c = client()
    assert c.get(r"/api/video/..\secret/file").status_code == 404
    assert c.get("/api/video/..%2Fsecret/file").status_code in (404, 405)


def test_scores_returns_latest_valid_dimension(tmp_env):
    c = client()
    storage.insert_objective_score("v", "D03", {
        "value": 6.0, "confidence": 0.9, "note": "本地信号: old"
    }, "signal_local", "local_cpu")
    storage.insert_objective_score("v", "D03", {
        "value": 7.0, "confidence": 0.9, "note": "本地信号: new"
    }, "signal_local", "local_cpu")
    storage.insert_objective_score("v", "D01", {
        "value": None, "confidence": None, "note": "LMM_UNAVAILABLE"
    }, "lmm_test", "test")
    r = c.get("/api/scores", params={"video_id": "v"})
    assert r.json() == {
        "D03": {"value": 7.0, "confidence": 0.9, "note": "本地信号: new",
                "method": "objective"}
    }
