# -*- coding: utf-8 -*-
"""FastAPI layer for the visual front-end: routing only.

All domain logic (storage, metrics, LMM calls, vision probing) lives in
the core package; this module stays a thin HTTP adapter.
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import webbrowser

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core import (
    DIMENSIONS,
    MAX_UPLOAD_MB,
    TEMPORAL_SIGNAL_DIMS,
    add_video,
    auto_evaluate,
    delete_video,
    get_conn,
    get_video_path,
    init_db,
    insert_objective_score,
    list_videos,
    probe_vision,
    signal_metrics,
)

MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _web_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


WEB_DIR = _web_dir()

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
    tmp_dir = tempfile.mkdtemp()
    tmp_path = None
    try:
        tmp_path = os.path.join(tmp_dir, os.path.basename(file.filename or "upload.mp4"))
        written = 0
        with open(tmp_path, "wb") as tmp:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过上限 {MAX_UPLOAD_MB}MB")
                tmp.write(chunk)
        return add_video(tmp_path, prompt_text, model_tag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@server.get("/api/videos")
def api_list_videos():
    return list_videos()


@server.get("/api/scores")
def api_scores(video_id: str):
    """Latest objective score per dimension for a video (newest wins)."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT scores FROM scores
                 WHERE video_id=? AND method='objective'
                 ORDER BY created_at DESC""", (video_id,))
    rows = c.fetchall()
    conn.close()
    out = {}
    for (sc_json,) in rows:
        sc = json.loads(sc_json)
        for dim_id, val in sc.items():
            if (dim_id not in out and isinstance(val, dict)
                    and val.get("value") is not None):
                out[dim_id] = {"value": val.get("value"),
                               "confidence": val.get("confidence"),
                               "note": val.get("note", ""),
                               "method": "objective"}
    return out


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
        raise HTTPException(status_code=404, detail="视频不存在") from None
    except PermissionError:
        raise HTTPException(
            status_code=409, detail="文件正在被使用，请关闭播放后重试") from None


@server.post("/api/check-vision")
def check_vision(base_url: str = Form(...), api_key: str = Form(...),
                 model: str = Form(...)):
    return probe_vision(base_url, api_key, model)


@server.post("/api/evaluate/{dim_id}")
def evaluate(dim_id: str, video_id: str = Form(...),
             prompt_text: str = Form(""), base_url: str = Form(""),
             api_key: str = Form(""), model: str = Form(""),
             n_frames: int = Form(8)):
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
           "n_frames": max(1, min(int(n_frames), 32)),
           "temperature": 0.0, "samplings": 1}
    res = auto_evaluate(video_id, [dim_id], cfg, prompt_text).get(
        dim_id, {"value": None, "confidence": None, "note": "EVALUATION_FAILED"})
    if res.get("value") is None:
        raise HTTPException(
            status_code=502,
            detail=f"评测失败：{res.get('note') or 'LMM_UNAVAILABLE'}")
    insert_objective_score(video_id, dim_id, res,
                           rater="lmm_" + model, model=model,
                           task_id="task_web")
    return {"dim_id": dim_id, **res, "method": "objective"}


# Static front-end last so /api routes take precedence.
server.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    no_browser = os.environ.get("VIDEOEVAL_NO_BROWSER", "").lower() in {"1", "true", "yes"}
    if not no_browser:
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    if sys.stderr is None:
        uvicorn.run(server, host="127.0.0.1", port=8765, log_config=None)
    else:
        uvicorn.run(server, host="127.0.0.1", port=8765)
