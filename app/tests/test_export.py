# -*- coding: utf-8 -*-
import json

from core import storage
from core.export import _human_score_rows, export_vbench


def test_expert_overrides_subjective(tmp_env, real_video):
    vid = storage.add_video(real_video)["video_id"]
    storage.save_subjective(vid, "user", "r1", {"D01": 3, "D08": 4}, "physical", "", "", "")
    storage.save_subjective(vid, "user", "r2", {"D01": 5, "D08": 6}, "physical", "", "", "")
    storage.save_subjective(vid, "expert", "exp", {"D01": 9, "D08": 2},
                            "physical", "", "", "")
    rows = {vid: sc for vid, tag, sc in _human_score_rows()}
    assert rows[vid]["D01"]["value"] == 9
    assert rows[vid]["D08"]["value"] == 2


def test_latest_expert_arbitration_wins(tmp_env, real_video):
    vid = storage.add_video(real_video)["video_id"]
    storage.save_subjective(vid, "expert", "exp", {"D01": 4}, "na", "", "", "")
    storage.save_subjective(vid, "expert", "exp", {"D01": 9}, "na", "", "", "")
    rows = {video_id: sc for video_id, _tag, sc in _human_score_rows()}
    assert rows[vid]["D01"]["value"] == 9


def test_invalid_expert_arbitration_does_not_override(tmp_env, real_video):
    vid = storage.add_video(real_video)["video_id"]
    storage.save_subjective(vid, "user", "r1", {"D08": 6}, "physical", "", "", "")
    storage.save_subjective(vid, "expert", "exp", {"D08": 2},
                            "technical", "", "", "")
    rows = {video_id: sc for video_id, _tag, sc in _human_score_rows()}
    assert rows[vid]["D08"] == 6.0


def test_partial_expert_arbitration_overlays_only_rated_dimensions(tmp_env, real_video):
    vid = storage.add_video(real_video)["video_id"]
    storage.save_subjective(vid, "user", "r1", {"D01": 5, "D08": 4}, "physical", "", "", "")
    storage.save_subjective(vid, "user", "r2", {"D01": 7, "D08": 6}, "physical", "", "", "")
    storage.save_subjective(vid, "expert", "exp", {"D08": 2}, "physical", "", "", "")
    rows = {video_id: sc for video_id, _tag, sc in _human_score_rows()}
    assert rows[vid]["D01"] == 6.0
    assert rows[vid]["D08"]["value"] == 2


def test_export_vbench_writes_leaderboard(tmp_env):
    storage.save_subjective("v", "user", "r1", {"D01": 7}, "na", "", "", "")
    out = export_vbench()
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["export_version"] == "vbench_compat_1.0"
    assert isinstance(data["leaderboard"], list)
    assert str(out).replace("/", "\\").endswith("data\\vbench_export.json")
