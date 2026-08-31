# -*- coding: utf-8 -*-
"""Core domain logic shared by the Gradio UI and the FastAPI web server.

Single source of truth: storage, media handling, LMM calls, local signal
metrics, statistics and VBench export all live here. UI layers stay thin.
"""
from .dimensions import (DIMENSIONS, DIM_IDS, DIM_NAME, DEFAULT_SPEC_ID,
                         TEMPORAL_SIGNAL_DIMS)
from .storage import (BASE, DATA, VIDEOS_DIR, FRAMES_DIR, DB, CONFIG_PATH,
                      MAX_UPLOAD_MB, get_conn, init_db, load_config, save_config,
                      add_video, delete_video, get_video_path, list_videos,
                      save_subjective, insert_objective_score)
from .media import md5_file, video_meta, validate_video, sample_frames, frame_to_b64
from .lmm import build_dim_prompt, score_one_dim, probe_vision
from .evaluate import signal_metrics, auto_evaluate
from .stats import compute_icc_matrix
from .export import _human_score_rows, _dim_value, dashboard_data, export_vbench

__all__ = [
    "DIMENSIONS", "DIM_IDS", "DIM_NAME", "DEFAULT_SPEC_ID", "TEMPORAL_SIGNAL_DIMS",
    "BASE", "DATA", "VIDEOS_DIR", "FRAMES_DIR", "DB", "CONFIG_PATH",
    "get_conn", "init_db", "load_config", "save_config", "MAX_UPLOAD_MB",
    "add_video", "delete_video", "get_video_path", "list_videos",
    "save_subjective", "insert_objective_score",
    "md5_file", "video_meta", "validate_video", "sample_frames", "frame_to_b64",
    "build_dim_prompt", "score_one_dim", "probe_vision",
    "signal_metrics", "auto_evaluate",
    "compute_icc_matrix", "_human_score_rows", "_dim_value", "dashboard_data",
    "export_vbench",
]
