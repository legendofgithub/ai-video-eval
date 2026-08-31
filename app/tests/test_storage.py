# -*- coding: utf-8 -*-
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
    assert len(storage.list_videos()) == 1


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
    assert "is_valid=1" in r_phys
    assert "is_valid=0" in r_na


def test_subjective_rejects_out_of_range_and_unknown_dims(tmp_env):
    with pytest.raises(ValueError, match="0-10"):
        storage.save_subjective("v", "user", "u1", {"D01": 10.1},
                                "na", "", "", "")
    with pytest.raises(ValueError, match="未知评测维度"):
        storage.save_subjective("v", "user", "u1", {"D99": 5},
                                "na", "", "", "")
