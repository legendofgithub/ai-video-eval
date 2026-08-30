# -*- coding: utf-8 -*-
"""FastAPI layer for the visual front-end: routing only.

All domain logic (storage, metrics, LMM calls, vision probing) lives in
the core package; this module stays a thin HTTP adapter.
"""
import os
import shutil
import tempfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core import (DIMENSIONS, TEMPORAL_SIGNAL_DIMS, add_video, auto_evaluate,
                  delete_video, get_video_path, init_db, insert_objective_score,
                  list_videos, probe_vision, signal_metrics)

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")

init_db()

server = FastAPI(title="AI Video Evaluation")


@server.get("/api/health")
def health():
    return {"ok": True, "dimensions": len(DIMENSIONS)}


@server.get("/api/dimensions")
def dimensions():
    return [{
        "dim_id": d["dim_id"], "name": d["name"], "layer": d["layer"],
        "anchor_low": d["anchor_low"], "anchor_mid": d["anchor_mid"],
        "anchor_high": d["anchor_high"],
        "needs_vision": d["dim_id"] not in TEMPORAL_SIGNAL_DIMS,
    } for d in DIMENSIONS]


@server.post("/api/upload")
async def upload_video(file: UploadFile = File(...),
                       prompt_text: str = Form(""),
                       model_tag: str = Form("")):
    """Stream the upload to a temp file, then delegate validation, size
    limits and dedup to core.add_video."""
    suffix = os.path.splitext(file.filename or "")[1].lower()
    tmp_dir = tempfile.mkdtemp()
    tmp_path = None
    try:
        tmp_path = os.path.join(tmp_dir, os.path.basename(file.filename or "upload.mp4"))
        with open(tmp_path, "wb") as tmp:
            tmp.write(await file.read())
        return add_video(tmp_path, prompt_text, model_tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@server.get("/api/videos")
def api_list_videos():
    return list_videos()


@server.get("/api/video/{video_id}/file")
def video_file(video_id: str):
    p = get_video_path(video_id)
    if not p:
        raise HTTPException(status_code=404, detail="视频不存在")
    return FileResponse(p)


@server.delete("/api/video/{video_id}")
def api_delete_video(video_id: str):
    try:
        return delete_video(video_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="视频不存在")
    except PermissionError:
        raise HTTPException(status_code=409,
                            detail="文件正在被使用，请关闭播放后重试")


@server.post("/api/check-vision")
async def check_vision(base_url: str = Form(...), api_key: str = Form(...),
                       model: str = Form(...)):
    return probe_vision(base_url, api_key, model)


@server.post("/api/evaluate/{dim_id}")
async def evaluate(dim_id: str, video_id: str = Form(...),
                   prompt_text: str = Form(""),
                   base_url: str = Form(""), api_key: str = Form(""),
                   model: str = Form("")):
    """Score one dimension through the shared core pipeline and persist it."""
    dim = next((d for d in DIMENSIONS if d["dim_id"] == dim_id), None)
    if not dim:
        raise HTTPException(status_code=404, detail="未知维度")
    if not get_video_path(video_id):
        raise HTTPException(status_code=404, detail="视频不存在")

    if dim_id in TEMPORAL_SIGNAL_DIMS:
        res = signal_metrics(get_video_path(video_id), [dim_id])[dim_id]
        insert_objective_score(video_id, dim_id, res,
                               rater="signal_local", model="local_cpu",
                               task_id="task_web")
        return {"dim_id": dim_id, **res, "method": "objective"}

    if not (base_url and api_key and model):
        raise HTTPException(status_code=400, detail="请提供测试用视觉模型")
    cfg = {"base_url": base_url, "api_key": api_key, "model": model,
           "n_frames": 8, "temperature": 0.0, "samplings": 1}
    res = auto_evaluate(video_id, [dim_id], cfg, prompt_text).get(
        dim_id, {"value": None, "confidence": None, "note": "EVALUATION_FAILED"})
    insert_objective_score(video_id, dim_id, res,
                           rater="lmm_" + model, model=model,
                           task_id="task_web")
    return {"dim_id": dim_id, **res, "method": "objective"}


# Static front-end last so /api routes take precedence.
server.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(server, host="127.0.0.1", port=8765)
