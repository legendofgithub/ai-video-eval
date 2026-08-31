# -*- coding: utf-8 -*-
import json

from core import storage
from core import export
from core.export import _human_score_rows, export_vbench


def test_expert_overrides_subjective(tmp_env, real_video):
    vid = storage.add_video(real_video)["video_id"]
    storage.save_subjective(vid, "user", "r1", {"D01": 3, "D08": 4}, "physical", "", "", "")
    storage.save_subjective(vid, "user", "r2", {"D01": 5, "D08": 6}, "physical", "", "", "")
    storage.save_subjective(vid, "expert", "exp", {"D01": 9, "D08": 2}, "na", "", "", "")
    rows = {vid: sc for vid, tag, sc in _human_score_rows()}
    assert rows[vid]["D01"]["value"] == 9
    assert rows[vid]["D08"]["value"] == 2


def test_export_vbench_writes_leaderboard(tmp_env, monkeypatch):
    monkeypatch.setattr(export, "BASE", str(tmp_env))
    storage.save_subjective("v", "user", "r1", {"D01": 7}, "na", "", "", "")
    out = export_vbench()
    data = json.loads(open(out, encoding="utf-8").read())
    assert data["export_version"] == "vbench_compat_1.0"
    assert isinstance(data["leaderboard"], list)
