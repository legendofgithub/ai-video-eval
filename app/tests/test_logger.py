# -*- coding: utf-8 -*-
"""Logger runtime-path contracts."""
from pathlib import Path

from core import logger
from core.logger import get_logger


def test_windowed_executable_logs_next_to_exe(tmp_path, monkeypatch):
    exe = tmp_path / "VideoEvalWeb.exe"
    monkeypatch.setattr(logger.sys, "frozen", True, raising=False)
    monkeypatch.setattr(logger.sys, "executable", str(exe))
    assert logger._app_base() == str(tmp_path)


def test_pytest_logging_is_isolated(tmp_path):
    probe = get_logger("videoeval.isolation_probe")
    paths = [Path(handler.baseFilename) for handler in probe.handlers
             if hasattr(handler, "baseFilename")]
    assert paths == [tmp_path / "runtime-data" / "app.log"]
