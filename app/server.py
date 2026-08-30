# -*- coding: utf-8 -*-
"""FastAPI server for the visual evaluation front-end.

Reuses the SQLite storage, local signal metrics (D03/D04) and LMM scoring
helpers from app.py. The browser front-end is served from ./web.
"""
import base64
import io
import json
import os
import datetime
import uuid
import sys
import shutil

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as core  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")

core.init_db()

server = FastAPI(title="AI Video Evaluation")


@server.get("/api/health")
def health():
    return {"ok": True, "dimensions": len(core.DIMENSIONS)}


@server.get("/api/dimensions")
def dimensions():
    out = []
    for d in core.DIMENSIONS:
        out.append({
            "dim_id": d["dim_id"], "name": d["name"], "layer": d["layer"],
            "anchor_low": d["anchor_low"], "anchor_mid": d["anchor_mid"],
            "anchor_high": d["anchor_high"],
            "needs_vision": d["dim_id"] not in core.TEMPORAL_SIGNAL_DIMS,
        })
    return out


@server.post("/api/upload")
async def upload_video(file: UploadFile = File(...),
                       prompt_text: str = Form(""),
                       model_tag: str = Form("")):
    """Store an uploaded video and return its metadata. MD5 duplicates
    resolve to the existing record instead of creating a new task."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".mp4", ".webm", ".mov"):
        raise HTTPException(status_code=400, detail="仅支持 mp4/webm/mov")
    vid = uuid.uuid4().hex[:8]
    dst = os.path.join(core.VIDEOS_DIR, f"{vid}{ext}")
    with open(dst, "wb") as f:
        f.write(await file.read())
    h = core.md5_file(dst)

    conn = core.get_conn(); c = conn.cursor()
    c.execute("SELECT video_id FROM videos WHERE file_hash=?", (h,))
    dup = c.fetchone()
    if dup:
        conn.close()
        os.remove(dst)
        return {"video_id": dup[0], "duplicate": True}

    fps, frames, w, hgt, dur = core.video_meta(dst)
    thumb_dir = os.path.join(core.FRAMES_DIR, vid)
    core.sample_frames(dst, 1, thumb_dir)
    thumb = os.path.join(thumb_dir, "f0000.jpg") if os.path.exists(
        os.path.join(thumb_dir, "f0000.jpg")) else None
    c.execute("INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (vid, os.path.basename(file.filename or dst), "upload", None, h,
               round(dur, 2), int(fps or 24), f"{w}x{hgt}",
               round(os.path.getsize(dst) / 1e6, 2), prompt_text, model_tag,
               datetime.datetime.now().isoformat(), thumb))
    conn.commit(); conn.close()
    return {
        "video_id": vid, "duplicate": False, "filename": file.filename,
        "duration_sec": round(dur, 2), "fps": int(fps or 24),
        "resolution": f"{w}x{hgt}",
        "file_size_mb": round(os.path.getsize(dst) / 1e6, 2),
    }


@server.get("/api/videos")
def list_videos():
    conn = core.get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, filename, model_tag, resolution,
                        duration_sec, created_at FROM videos
                 ORDER BY created_at DESC LIMIT 20""")
    rows = c.fetchall(); conn.close()
    return [{"video_id": r[0], "filename": r[1], "model_tag": r[2],
             "resolution": r[3], "duration_sec": r[4], "created_at": r[5]}
            for r in rows]


@server.get("/api/video/{video_id}/file")
def video_file(video_id: str):
    p = core.get_video_path(video_id)
    if not p:
        raise HTTPException(status_code=404, detail="视频不存在")
    return FileResponse(p)


@server.delete("/api/video/{video_id}")
def delete_video(video_id: str):
    """Remove a video record, its scores, the file and extracted frames."""
    conn = core.get_conn(); c = conn.cursor()
    c.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="视频不存在")
    c.execute("DELETE FROM scores WHERE video_id=?", (video_id,))
    c.execute("DELETE FROM videos WHERE video_id=?", (video_id,))
    conn.commit(); conn.close()

    p = core.get_video_path(video_id)
    if p:
        try:
            os.remove(p)
        except PermissionError:
            raise HTTPException(status_code=409,
                                detail="文件正在被使用，请关闭播放后重试")
    shutil.rmtree(os.path.join(core.FRAMES_DIR, video_id),
                  ignore_errors=True)
    return {"ok": True, "deleted": video_id}


def _vision_test_image() -> str:
    """64x64 red circle PNG as base64 data URL."""
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=(230, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@server.post("/api/check-vision")
async def check_vision(base_url: str = Form(...), api_key: str = Form(...),
                       model: str = Form(...)):
    """Probe whether the configured model can actually see images:
    send a red circle and require the reply to name shape and color."""
    if not (base_url and api_key and model):
        return {"has_vision": False, "reason": "配置不完整"}
    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        content = [
            {"type": "text", "text": "请描述这张图片中的形状和颜色，不超过10个字。"},
            {"type": "image_url", "image_url": {"url": _vision_test_image()}},
        ]
        resp = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "user", "content": content}])
        txt = (resp.choices[0].message.content or "").strip()
        has_shape = any(k in txt for k in ("圆", "circle", "Circular", "circular"))
        has_color = any(k in txt for k in ("红", "red", "Red"))
        if has_shape and has_color:
            return {"has_vision": True, "reply": txt}
        return {"has_vision": False, "reason": f"模型未能正确描述测试图：{txt[:60]}"}
    except Exception as e:
        return {"has_vision": False, "reason": f"API_ERROR: {e}"}


@server.post("/api/evaluate/{dim_id}")
async def evaluate(dim_id: str, video_id: str = Form(...),
                   prompt_text: str = Form(""),
                   base_url: str = Form(""), api_key: str = Form(""),
                   model: str = Form("")):
    """Score one dimension. D03/D04 run local CPU metrics; the other eight
    call the user's vision LLM. Results are persisted in the scores table."""
    dim = next((d for d in core.DIMENSIONS if d["dim_id"] == dim_id), None)
    if not dim:
        raise HTTPException(status_code=404, detail="未知维度")
    vpath = core.get_video_path(video_id)
    if not vpath:
        raise HTTPException(status_code=404, detail="视频不存在")

    if dim_id in core.TEMPORAL_SIGNAL_DIMS:
        res = core.signal_metrics(vpath, [dim_id])[dim_id]
        method, rater, used_model = "objective", "signal_local", "local_cpu"
    else:
        if not (base_url and api_key and model):
            raise HTTPException(status_code=400, detail="请提供测试用视觉模型")
        client = OpenAI(base_url=base_url, api_key=api_key)
        frame_paths = core.sample_frames(vpath, 8,
                                         os.path.join(core.FRAMES_DIR, video_id))
        if not frame_paths:
            raise HTTPException(status_code=500, detail="抽帧失败，无法评测")
        res = core.score_one_dim(client, model, dim, frame_paths, prompt_text, 0.0)
        method, rater, used_model = "objective", "lmm_" + model, model

    conn = core.get_conn(); c = conn.cursor()
    c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (uuid.uuid4().hex[:10], "task_web", video_id,
               core.DEFAULT_SPEC_ID, rater, "lmm_auto", method, used_model,
               json.dumps({dim_id: res}, ensure_ascii=False), None, 1,
               datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()
    return {"dim_id": dim_id, **res, "method": method}


# Static front-end last so /api routes take precedence.
server.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(server, host="127.0.0.1", port=8765)
