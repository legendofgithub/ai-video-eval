# -*- coding: utf-8 -*-
"""Dashboard aggregation endpoint (GET /api/dashboard)."""
from fastapi.testclient import TestClient

import server as server_mod
from core import storage


def client():
    return TestClient(server_mod.server)


def test_dashboard_empty_structure():
    d = client().get("/api/dashboard").json()
    assert d["videos"] == []
    assert d["models"] == []
    assert len(d["mos_hist"]) == 10
    assert sum(h["count"] for h in d["mos_hist"]) == 0
    assert d["summary"]["n_videos"] == 0
    assert d["world_model"] == []


def test_dashboard_aggregates_scores(tmp_env):
    conn = storage.get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO videos (video_id, filename, model_tag) VALUES (?,?,?)",
                ("v1", "ad.mp4", "Sora"))
    conn.commit(); conn.close()

    c = client()
    storage.insert_objective_score("v1", "D01",
                                    {"value": 8.0, "confidence": 0.9, "note": "x"}, "lmm_a", "m")
    storage.insert_objective_score("v1", "D01",
                                    {"value": 6.0, "confidence": 0.9, "note": "x"}, "lmm_a", "m")
    storage.insert_objective_score("v1", "D08",
                                    {"value": 4.0, "confidence": 0.9, "note": "x"}, "lmm_a", "m")
    storage.save_subjective("v1", "user", "r1", {"D02": 5}, "na", "", "", "")

    d = c.get("/api/dashboard").json()
    v = d["videos"][0]
    assert v["video_id"] == "v1"
    assert v["model_tag"] == "Sora"
    assert v["mean_scores"]["D01"] == 7.0          # (8+6)/2
    assert v["mean_scores"]["D08"] == 4.0
    assert v["objective_mean_scores"]["D01"] == 7.0
    assert v["human_mean_scores"]["D02"] == 5.0
    assert d["models"][0]["model_tag"] == "Sora"
    assert sum(h["count"] for h in d["mos_hist"]) == 1
    assert d["world_model"][0]["D08"] == 4.0
    assert d["summary"]["n_ratings"] == 4
    assert d["summary"]["overall_mean"] == 5.75     # all score values; MOS is separate


def test_dashboard_expert_overrides_subjective_per_dimension(tmp_env):
    conn = storage.get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO videos (video_id, filename, model_tag) VALUES (?,?,?)",
                ("v1", "clip.mp4", "Sora"))
    conn.commit(); conn.close()

    storage.insert_objective_score("v1", "D08",
                                   {"value": 8.0, "confidence": 0.9, "note": "x"},
                                   "lmm", "vision")
    for rater, score in (("r1", 6.0), ("r2", 4.0)):
        storage.save_subjective("v1", "user", rater, {"D01": 5, "D08": score},
                                "physical", "", "", "")
    storage.save_subjective("v1", "expert", "exp", {"D08": 2},
                            "physical", "", "", "")

    d = client().get("/api/dashboard").json()
    v = d["videos"][0]
    assert v["mean_scores"]["D01"] == 5.0
    assert v["mean_scores"]["D08"] == 5.0
    assert sum(h["count"] for h in d["mos_hist"]) == 2


def test_dashboard_ignores_invalid_expert_arbitration(tmp_env):
    conn = storage.get_conn(); cur = conn.cursor()
    cur.execute("INSERT INTO videos (video_id, filename, model_tag) VALUES (?,?,?)",
                ("v1", "clip.mp4", "Sora"))
    conn.commit(); conn.close()

    storage.save_subjective("v1", "user", "r1", {"D08": 6}, "physical", "", "", "")
    storage.save_subjective("v1", "expert", "exp", {"D08": 2},
                            "technical", "", "", "")

    v = client().get("/api/dashboard").json()["videos"][0]
    assert v["mean_scores"]["D08"] == 6.0
