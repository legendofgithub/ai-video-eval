# -*- coding: utf-8 -*-
"""Evaluation orchestration: local signal metrics + LMM routing."""
import os

import cv2
import numpy as np
from openai import OpenAI

from .dimensions import DIMENSIONS, TEMPORAL_SIGNAL_DIMS
from .lmm import score_one_dim
from .logger import get_logger
from .media import sample_frames
from .storage import FRAMES_DIR, get_video_path, load_config

log = get_logger("videoeval.evaluate")


def _sample_gray_frames(path, n=24, size=(320, 180)):
    """Uniformly sample frames as resized grayscale arrays (no disk writes)."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total == 0:
        cap.release(); return []
    idxs = [int(i * total / n) for i in range(n)]
    grays = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(i, total - 1))
        ok, f = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, size)
        grays.append(g)
    cap.release()
    return grays


def _flicker_score(grays):
    """D03: Laplacian-edge temporal instability + frame-diff jitter."""
    n = len(grays)
    if n < 2:
        return None, "帧数不足"
    lap = np.array([cv2.Laplacian(g, cv2.CV_64F).var() for g in grays])
    lap_cv = lap.std() / (lap.mean() + 1e-6)
    diffs = np.array([np.abs(grays[i].astype(float) - grays[i - 1].astype(float)).mean()
                      for i in range(1, n)])
    diff_cv = diffs.std() / (diffs.mean() + 1e-6)
    flicker_idx = 0.6 * lap_cv + 0.4 * diff_cv
    score = float(np.clip(10 * np.exp(-flicker_idx * 0.8), 0, 10))
    return round(score, 2), f"本地信号: 闪烁指数={flicker_idx:.3f}(边缘CV={lap_cv:.3f},帧差CV={diff_cv:.3f})"


def _motion_smooth_score(grays):
    """D04: Farneback optical-flow motion-magnitude jerk, size normalized."""
    n = len(grays)
    if n < 3:
        return None, "帧数不足"
    mags = []
    for i in range(1, n):
        flow = cv2.calcOpticalFlowFarneback(
            grays[i - 1], grays[i], None, 0.5, 3, 15, 3, 5, 1.2, 0)
        mag = float(np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean())
        mags.append(mag)
    mags = np.array(mags)
    jerk = np.abs(np.diff(mags))
    mean_motion = mags.mean()
    norm_jerk = jerk.mean() / (mean_motion + 1e-6)
    score = float(np.clip(10 * np.exp(-norm_jerk * 0.5), 0, 10))
    return round(score, 2), f"本地信号: 归一化运动突变={norm_jerk:.3f}(均值光流={mean_motion:.3f})"


def signal_metrics(video_path, dims):
    """Local CPU metrics for D03/D04. Returns {dim_id: {value,confidence,note}}."""
    grays = _sample_gray_frames(video_path, n=24)
    out = {}
    if "D03" in dims:
        v, note = _flicker_score(grays)
        out["D03"] = {"value": v, "confidence": 0.9 if v is not None else None, "note": note}
    if "D04" in dims:
        v, note = _motion_smooth_score(grays)
        out["D04"] = {"value": v, "confidence": 0.9 if v is not None else None, "note": note}
    return out


def auto_evaluate(video_id, dims, lmm_cfg=None, prompt_text=None):
    """Score dimensions: D03/D04 locally; the rest via vision LMM.

    lmm_cfg is a flat LMM config dict (base_url/api_key/model/...). When
    None, the on-disk config is used. Per-dimension failures do not block
    other dimensions.
    """
    results = {}
    local_dims = [d for d in dims if d in TEMPORAL_SIGNAL_DIMS]
    if local_dims:
        vpath = get_video_path(video_id)
        if vpath:
            results.update(signal_metrics(vpath, local_dims))
        else:
            for d in local_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_VIDEO_FILE"}

    lmm_dims = [d for d in dims if d not in TEMPORAL_SIGNAL_DIMS]
    if not lmm_dims:
        return results
    try:
        cfg = lmm_cfg if lmm_cfg is not None else load_config()["lmm"]
        client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], timeout=60)
        vpath = get_video_path(video_id)
        if not vpath:
            for d in lmm_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_VIDEO_FILE"}
            return results
        frame_paths = sample_frames(vpath, cfg.get("n_frames", 8),
                                    os.path.join(FRAMES_DIR, video_id))
        if not frame_paths:
            for d in lmm_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_FRAMES"}
            return results
        for dim_id in lmm_dims:
            dim = next(d for d in DIMENSIONS if d["dim_id"] == dim_id)
            agg = None
            for _ in range(max(1, cfg.get("samplings", 1))):
                r = score_one_dim(client, cfg["model"], dim, frame_paths,
                                  prompt_text, cfg.get("temperature", 0.0))
                if r["value"] is None:
                    results[dim_id] = r
                    break
                if agg is None:
                    agg = {"value": [], "confidence": [], "note": r["note"]}
                agg["value"].append(r["value"]); agg["confidence"].append(r["confidence"])
            else:
                results[dim_id] = {"value": round(float(np.mean(agg["value"])), 2),
                                   "confidence": round(float(np.mean(agg["confidence"])), 2),
                                   "note": agg["note"]}
    except Exception as e:
        log.warning("LMM unavailable: %s", e)
        for d in lmm_dims:
            if d not in results:
                results[d] = {"value": None, "confidence": None,
                              "note": f"LMM_UNAVAILABLE: {e}"}
    return results
