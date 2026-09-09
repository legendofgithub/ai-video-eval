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
def isolated_db():
    return storage.DB


def _make_mp4(path):
    h, w = 48, 64
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
    for i in range(6):
        frame = np.full((h, w, 3), (i * 40 % 255, 120, 160), np.uint8)
        vw.write(frame)
    vw.release()


def _upload(client, tmp_path, model_tag=""):
    mp = tmp_path / "clip.mp4"
    _make_mp4(mp)
    r = client.post("/api/upload", files={
        "file": ("clip.mp4", mp.read_bytes(), "video/mp4")
    }, data={"model_tag": model_tag})
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


def test_model_tags_distinct_with_counts(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    # Distinct file contents (different frame counts): identical files would
    # be deduped to the first record, so later tags would never persist.
    for frames, tag in ((6, "kling"), (9, "kling"), (12, "jimeng")):
        mp = tmp_path / f"clip_{frames}.mp4"
        h, w = 48, 64
        vw = cv2.VideoWriter(str(mp), cv2.VideoWriter_fourcc(*"mp4v"), 10, (w, h))
        for i in range(frames):
            vw.write(np.full((h, w, 3), (i * 40 % 255, 120, 160), np.uint8))
        vw.release()
        r = c.post("/api/upload", files={
            "file": (mp.name, mp.read_bytes(), "video/mp4")
        }, data={"model_tag": tag})
        assert r.status_code == 200, r.text
    r = c.get("/api/model-tags")
    assert r.status_code == 200
    tags = {t["model_tag"]: t["count"] for t in r.json()}
    assert tags == {"kling": 2, "jimeng": 1}
    assert list(tags) == ["kling", "jimeng"]  # most-used first


def test_evaluate_all_without_lmm(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    vid = _upload(c, tmp_path)
    r = c.post("/api/evaluate-all", data={"video_id": vid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["D03"]["value"] is not None
    assert body["D04"]["value"] is not None
    for d in ("D01", "D02", "D05", "D06", "D07", "D08", "D09", "D10"):
        assert body[d]["value"] is None
    # Only successful local dims may persist.
    persisted = c.get(f"/api/scores?video_id={vid}").json()
    assert "D03" in persisted and "D04" in persisted
    assert "D01" not in persisted


def test_records_roundtrip(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    vid = _upload(c, tmp_path)
    assert c.post("/api/records", json={"video_id": "nope"}).status_code == 404

    r = c.post("/api/records", json={"video_id": vid})
    assert r.status_code == 200, r.text
    assert r.json()["scores"]["D01"] is None

    storage.insert_objective_score(vid, "D05", {"value": 7.5}, "t", "m")
    c.post("/api/records", json={"video_id": vid})
    rows = c.get("/api/records").json()
    assert len(rows) == 2
    assert rows[0]["filename"] == "clip.mp4"
    assert rows[0]["scores"]["D05"] == 7.5  # newest record first

    assert c.delete(f"/api/records/{rows[0]['record_id']}").status_code == 200
    assert c.delete("/api/records/nope").status_code == 404
    assert len(c.get("/api/records").json()) == 1


def test_duplicate_upload_is_idempotent(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    mp = tmp_path / "clip.mp4"
    _make_mp4(mp)
    bytes_a = mp.read_bytes()
    upload = {"file": ("clip.mp4", bytes_a, "video/mp4")}
    r1 = c.post("/api/upload", files=upload, data={"model_tag": "audit_edge"})
    r2 = c.post("/api/upload", files=upload, data={"model_tag": "audit_edge"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["model_tag"] == "audit_edge"
    assert r1.json()["duplicate"] is False
    assert r2.json()["duplicate"] is True
    assert r2.json()["video_id"] == r1.json()["video_id"]
    listed = c.get("/api/videos").json()
    assert listed[0]["model_tag"] == "audit_edge"
    assert len(list((tmp_path / "runtime-data" / "videos").glob("*.mp4"))) == 1


def test_subjective_rejects_empty_dimensions(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    vid = _upload(c, tmp_path)
    r = c.post("/api/score/subjective", json={
        "video_id": vid, "role": "user", "rater_id": "u_001",
        "dims": {}, "gate": "na"})
    assert r.status_code == 400
    assert "至少" in r.json()["detail"]


def test_subjective_rejects_blank_rater_and_unknown_gate(isolated_db, tmp_path):
    c = TestClient(server_mod.server)
    vid = _upload(c, tmp_path)
    blank = c.post("/api/score/subjective", json={
        "video_id": vid, "role": "user", "rater_id": " ",
        "dims": {"D01": 7}, "gate": "na"})
    gate = c.post("/api/score/subjective", json={
        "video_id": vid, "role": "user", "rater_id": "u_001",
        "dims": {"D01": 7}, "gate": "layout"})
    assert blank.status_code == 400
    assert gate.status_code == 400


def test_failed_local_signal_does_not_persist(isolated_db, monkeypatch):
    c = TestClient(server_mod.server)
    monkeypatch.setattr(server_mod, "get_video_path", lambda _vid: "clip.mp4")
    monkeypatch.setattr(server_mod, "signal_metrics", lambda _path, dims: {
        "D03": {"value": None, "confidence": None, "note": "帧数不足"}
    })
    r = c.post("/api/evaluate/D03", data={"video_id": "v"})
    assert r.status_code == 502
    assert "帧数不足" in r.json()["detail"]
    conn = storage.get_conn()
    assert conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0] == 0
    conn.close()


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
