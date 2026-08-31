# -*- coding: utf-8 -*-
"""Tests for the web workbench: subjective save, reliability and export."""
import os
import socket

import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from fastapi.testclient import TestClient

import core
import core.storage as storage
import server as server_mod


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the single SQLite file at a temp path and create tables there."""
    db = tmp_path / "iso.db"
    monkeypatch.setattr(storage, "DB", str(db))
    monkeypatch.setattr(core.export, "BASE", str(tmp_path))
    storage.init_db()
    yield str(db)


def _make_mp4(path):
    h, w = 48, 64
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(6):
        frame = np.full((h, w, 3), (i * 40 % 255, 120, 160), np.uint8)
        vw.write(frame)
    vw.release()


def _upload(client, tmp_path):
    mp = tmp_path / "clip.mp4"
    _make_mp4(mp)
    r = client.post("/api/upload", files={"file": ("clip.mp4", mp.read_bytes(), "video/mp4")})
    assert r.status_code == 200, r.text
    return r.json()["video_id"]


def test_subjective_missing_video_404():
    c = TestClient(server_mod.server)
    r = c.post("/api/score/subjective", json={
        "video_id": "nope", "dims": {"D01": 7}, "gate": "na"})
    assert r.status_code == 404


def test_is_port_free_probe():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    busy = s.getsockname()[1]
    assert server_mod.is_port_free(busy) is False
    s.close()
    assert server_mod.is_port_free(busy) is True


def test_duplicate_upload_is_idempotent(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    mp = tmp_path / "clip.mp4"
    _make_mp4(mp)
    bytes_a = mp.read_bytes()
    r1 = c.post("/api/upload", files={"file": ("clip.mp4", bytes_a, "video/mp4")})
    r2 = c.post("/api/upload", files={"file": ("clip.mp4", bytes_a, "video/mp4")})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r2.json()["video_id"] == r1.json()["video_id"]


def test_reliability_empty_structure():
    c = TestClient(server_mod.server)
    rows = c.get("/api/reliability").json()
    assert len(rows) == 10
    for r in rows:
        assert {"dim_id", "name", "icc", "krippendorff_alpha"} <= set(r)
        assert r["icc"] is None and r["krippendorff_alpha"] is None


def test_export_vbench_empty(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    r = c.get("/api/export/vbench")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "leaderboard" in r.json()


def test_subjective_flow_and_reliability(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    vid = _upload(c, tmp_path)
    # two raters, agreeing-ish scores
    for rid, score in [("u_001", 7.0), ("u_002", 6.5)]:
        r = c.post("/api/score/subjective", json={
            "video_id": vid, "role": "user", "rater_id": rid,
            "dims": {"D01": score, "D08": 8.0}, "gate": "na"})
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True
    rows = {r["dim_id"]: r for r in c.get("/api/reliability").json()}
    # D01 now has two raters across one unit -> computable (single unit still <2 units)
    assert rows["D01"]["icc"] is None  # need >=2 units (videos) for ICC
    # export should now carry the video's model tag once set
    c.post("/api/score/subjective", json={
        "video_id": vid, "role": "user", "rater_id": "u_003",
        "dims": {"D01": 7.0}, "gate": "na"})
    # set model tag via storage update for export coverage
    conn = storage.get_conn(); cur = conn.cursor()
    cur.execute("UPDATE videos SET model_tag='self_test' WHERE video_id=?", (vid,))
    conn.commit(); conn.close()
    exp = c.get("/api/export/vbench").json()
    assert any(m["model_tag"] == "self_test" for m in exp["leaderboard"])
