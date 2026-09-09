# -*- coding: utf-8 -*-
"""Shared fixtures: fully isolated storage dirs + a real test video."""
import logging
import os

import pytest

# Block the legacy-file migration so tests never move the developer's real
# evaluation.db / config.json out of the project root.
os.environ.setdefault("VIDEOEVAL_SKIP_MIGRATION", "1")

from core import storage
from core import logger

SRC_VIDEO = r"F:\AI\codex project\AI视频评测\测试用例\华清普智孵化器广告.mp4"


@pytest.fixture(autouse=True)
def _isolated_runtime_storage(tmp_path, monkeypatch):
    """Keep every test away from the developer's real DB/media directories."""
    data = tmp_path / "runtime-data"
    videos = data / "videos"
    frames = data / "frames"
    videos.mkdir(parents=True)
    frames.mkdir(parents=True)
    monkeypatch.setattr(storage, "DB", str(tmp_path / "evaluation.db"))
    monkeypatch.setattr(storage, "VIDEOS_DIR", str(videos))
    monkeypatch.setattr(storage, "FRAMES_DIR", str(frames))
    monkeypatch.setattr(storage, "CONFIG_PATH", str(tmp_path / "config.json"))
    monkeypatch.setattr(storage, "DATA", str(data))
    monkeypatch.setattr(logger, "_LOG_PATH", str(data / "app.log"))
    names = [name for name in logging.Logger.manager.loggerDict
             if name == "videoeval" or name.startswith("videoeval.")]
    saved_handlers = [(name, list(logging.getLogger(name).handlers)) for name in names]
    for _name, handlers in saved_handlers:
        logging.getLogger(_name).handlers = []
    storage.init_db()
    try:
        yield
    finally:
        for name, _handlers in saved_handlers:
            current = logging.getLogger(name)
            for handler in current.handlers:
                handler.close()
            current.handlers = []
            current.handlers.extend(_handlers)


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Redirect DB/videos/frames/config to a temp dir and re-init schema."""
    data = tmp_path / "data"
    videos = data / "videos"
    frames = data / "frames"
    videos.mkdir(parents=True)
    frames.mkdir(parents=True)
    monkeypatch.setattr(storage, "DB", str(tmp_path / "evaluation.db"))
    monkeypatch.setattr(storage, "DATA", str(data))
    monkeypatch.setattr(storage, "VIDEOS_DIR", str(videos))
    monkeypatch.setattr(storage, "FRAMES_DIR", str(frames))
    monkeypatch.setattr(storage, "CONFIG_PATH", str(tmp_path / "config.json"))
    storage.init_db()
    return tmp_path


@pytest.fixture()
def real_video():
    assert os.path.exists(SRC_VIDEO), f"缺少测试视频: {SRC_VIDEO}"
    return SRC_VIDEO
