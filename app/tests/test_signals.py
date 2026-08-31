# -*- coding: utf-8 -*-
from core import storage
from core.evaluate import auto_evaluate, signal_metrics
from core.media import sample_frames


def test_local_signal_metrics(tmp_env, real_video):
    r = storage.add_video(real_video)
    sig = signal_metrics(storage.get_video_path(r["video_id"]), ["D03", "D04"])
    assert sig["D03"]["value"] is not None
    assert sig["D04"]["value"] is not None
    assert "本地信号" in sig["D03"]["note"]


def test_auto_evaluate_local_only_without_key(tmp_env, real_video):
    r = storage.add_video(real_video)
    res = auto_evaluate(r["video_id"], ["D03", "D04"])
    assert res["D03"]["value"] is not None
    assert res["D04"]["value"] is not None


def test_auto_evaluate_degrades_lmm_dims_without_key(tmp_env, real_video):
    r = storage.add_video(real_video)
    res = auto_evaluate(r["video_id"], ["D01", "D03"])
    assert res["D03"]["value"] is not None
    assert res["D01"]["value"] is None
    assert "LMM_UNAVAILABLE" in res["D01"]["note"]


def test_sample_frames_clamps_non_positive_count(tmp_env, real_video):
    r = storage.add_video(real_video)
    paths = sample_frames(storage.get_video_path(r["video_id"]), 0,
                          str(tmp_env / "zero"))
    assert paths
