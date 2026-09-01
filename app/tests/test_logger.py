# -*- coding: utf-8 -*-
"""Logger runtime-path contracts."""
from core import logger


def test_windowed_executable_logs_next_to_exe(tmp_path, monkeypatch):
    exe = tmp_path / "VideoEvalWeb.exe"
    monkeypatch.setattr(logger.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logger.sys, "executable", str(exe))
    assert logger._app_base() == str(tmp_path)
