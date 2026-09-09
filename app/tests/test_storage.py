# -*- coding: utf-8 -*-
import json

import pytest

from core import storage


def test_rejects_invalid_video(tmp_env, tmp_path):
    fake = tmp_env / "fake.mp4"
    fake.write_bytes(b"\x00" * 1024)
    with pytest.raises(ValueError):
        storage.add_video(str(fake))


def test_add_and_duplicate(tmp_env, real_video):
    r1 = storage.add_video(real_video, "p", "model_a")
    assert not r1["duplicate"]
    assert r1["resolution"] == "1280x720"
    r2 = storage.add_video(real_video, "p", "model_a")
    assert r2["duplicate"]
    assert r2["video_id"] == r1["video_id"]
    assert r2["filename"] == r1["filename"]
    assert r2["resolution"] == r1["resolution"]
    assert r2["model_tag"] == r1["model_tag"]
    listed = storage.list_videos()
    assert len(listed) == 1
    assert isinstance(listed[0]["fps"], int) and listed[0]["fps"] > 0


def test_delete_removes_file_and_records(tmp_env, real_video):
    r = storage.add_video(real_video)
    vid = r["video_id"]
    storage.insert_objective_score(vid, "D03", {"value": 6.0}, "t", "m")
    out = storage.delete_video(vid)
    assert out["ok"]
    assert storage.get_video_path(vid) is None
    assert storage.list_videos() == []


def test_delete_missing_raises(tmp_env):
    with pytest.raises(LookupError):
        storage.delete_video("no_such")


def test_gate_invalidates_mislabeled_low_scores(tmp_env):
    r_phys = storage.save_subjective("v", "user", "u1", {"D08": 3},
                                     "physical", "", "", "")
    r_na = storage.save_subjective("v", "user", "u2", {"D08": 3},
                                   "na", "", "", "")
    assert "有效维度=1/1" in r_phys
    assert "有效维度=0/1" in r_na


def test_per_dimension_gate_isolates_invalid_low_scores(tmp_env):
    detail = storage.save_subjective(
        "v", "user", "u1", {"D01": 7, "D05": 3, "D08": 3},
        "na", "", "", "",
        {"D05": "physical", "D08": "physical"},
    )
    assert "有效维度=2/3" in detail
    conn = storage.get_conn()
    rows = conn.execute(
        "SELECT scores, is_valid FROM scores WHERE video_id='v' ORDER BY is_valid"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    invalid_scores, invalid_flag = rows[0]
    valid_scores, valid_flag = rows[1]
    assert valid_flag == 1 and "D01" in valid_scores and "D08" in valid_scores
    assert invalid_flag == 0 and "D05" in invalid_scores


def test_per_dimension_gate_rejects_unknown_values(tmp_env):
    with pytest.raises(ValueError, match="未知低分门控类型"):
        storage.save_subjective("v", "user", "u1", {"D08": 3},
                                "na", "", "", "", {"D08": "layout"})
    with pytest.raises(ValueError, match="未知低分门控维度"):
        storage.save_subjective("v", "user", "u1", {"D08": 3},
                                "na", "", "", "", {"D99": "physical"})


def test_low_score_note_is_persisted_without_ab_choice(tmp_env):
    storage.save_subjective("v", "user", "u1", {"D08": 3, "D01": 7},
                            "physical", "悬浮 @ 00:03", "", "")
    conn = storage.get_conn()
    scores = json.loads(conn.execute(
        "SELECT scores FROM scores WHERE video_id='v' AND is_valid=1"
    ).fetchone()[0])
    conn.close()
    assert scores["D08"]["note"] == "悬浮 @ 00:03"
    assert scores["D01"]["note"] == ""


def test_subjective_rejects_out_of_range_and_unknown_dims(tmp_env):
    with pytest.raises(ValueError, match="0-10"):
        storage.save_subjective("v", "user", "u1", {"D01": 10.1},
                                "na", "", "", "")
    with pytest.raises(ValueError, match="未知评测维度"):
        storage.save_subjective("v", "user", "u1", {"D99": 5},
                                "na", "", "", "")


def test_legacy_files_migrate_into_data(tmp_path, monkeypatch):
    app = tmp_path / "app"
    data = app / "data"
    data.mkdir(parents=True)
    (app / "evaluation.db").write_bytes(b"old-db")
    (app / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(storage, "BASE", str(app))
    monkeypatch.setattr(storage, "DATA", str(data))
    monkeypatch.delenv("VIDEOEVAL_SKIP_MIGRATION", raising=False)

    db_path = storage._runtime_path("evaluation.db")
    cfg_path = storage._runtime_path("config.json")

    assert db_path == str(data / "evaluation.db")
    assert (data / "evaluation.db").read_bytes() == b"old-db"
    assert not (app / "evaluation.db").exists()
    assert cfg_path == str(data / "config.json")
    assert (data / "config.json").exists()


def test_migration_skipped_under_env_flag(tmp_path, monkeypatch):
    app = tmp_path / "app"
    data = app / "data"
    data.mkdir(parents=True)
    (app / "evaluation.db").write_bytes(b"old-db")
    monkeypatch.setattr(storage, "BASE", str(app))
    monkeypatch.setattr(storage, "DATA", str(data))
    monkeypatch.setenv("VIDEOEVAL_SKIP_MIGRATION", "1")

    assert storage._runtime_path("evaluation.db") == str(data / "evaluation.db")
    assert (app / "evaluation.db").exists()
    assert not (data / "evaluation.db").exists()
