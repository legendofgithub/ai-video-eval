# -*- coding: utf-8 -*-
"""Real DeepSeek vision tests. Skipped unless DEEPSEEK_API_KEY is set."""
import os

import pytest

from core.evaluate import auto_evaluate
from core.lmm import probe_vision

pytestmark = pytest.mark.skipif(
    not os.environ.get("DEEPSEEK_API_KEY"),
    reason="需要环境变量 DEEPSEEK_API_KEY",
)

BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash-vision-exp"


def test_vision_probe():
    r = probe_vision(BASE_URL, os.environ["DEEPSEEK_API_KEY"], MODEL)
    assert r["has_vision"], r


def test_auto_evaluate_d01(tmp_env, real_video):
    from core import storage
    r = storage.add_video(real_video)
    cfg = {"base_url": BASE_URL, "api_key": os.environ["DEEPSEEK_API_KEY"],
           "model": MODEL, "n_frames": 4, "temperature": 0.0, "samplings": 1}
    res = auto_evaluate(r["video_id"], ["D01"], cfg)
    assert res["D01"]["value"] is not None
