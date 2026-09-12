# -*- coding: utf-8 -*-
"""FastAPI layer for the visual front-end: routing only.

All domain logic (storage, metrics, LMM calls, vision probing) lives in
the core package; this module stays a thin HTTP adapter.
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import webbrowser
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import (
    DECKS_DIR,
    DIM_IDS,
    DIMENSIONS,
    MAX_UPLOAD_MB,
    TEMPORAL_SIGNAL_DIMS,
    add_deck,
    add_video,
    auto_evaluate,
    compute_icc_matrix,
    compute_krippendorff_alpha,
    dashboard_data,
    deck_dashboard_data,
    deck_slides_dir,
    delete_deck,
    delete_test_record,
    delete_video,
    export_vbench,
    get_conn,
    get_deck_path,
    get_video_path,
    init_db,
    insert_deck_objective_score,
    insert_objective_score,
    list_decks,
    list_test_records,
    list_videos,
    load_config,
    load_lmm_config_masked,
    probe_vision,
    save_lmm_config,
    save_subjective,
    save_test_record,
    signal_metrics,
)
from core import ppt as ppt_core
from core.logger import get_logger

MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_CHUNK_BYTES = 1024 * 1024


def is_port_free(port, host="127.0.0.1"):
    """Probe whether a TCP port can be bound (used before launch to detect
    a port already occupied by another instance)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            s.bind((host, port))
        except OSError:
            return False
        return True


def _web_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


WEB_DIR = _web_dir()
log = get_logger("videoeval.server")

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


@server.get("/api/model-tags")
def api_model_tags():
    """Distinct model tags with usage counts, most-used first.

    Feeds the upload form's autocomplete so the same model never splits
    into multiple leaderboard rows over spelling drift (可灵/kling/Kling).
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT model_tag, COUNT(*) AS n FROM videos
                 WHERE model_tag IS NOT NULL AND model_tag != ''
                 GROUP BY model_tag ORDER BY n DESC, model_tag""")
    rows = c.fetchall()
    conn.close()
    return [{"model_tag": r[0], "count": r[1]} for r in rows]


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


@server.post("/api/evaluate-all")
def evaluate_all(video_id: str = Form(...), prompt_text: str = Form(""),
                 base_url: str = Form(""), api_key: str = Form(""),
                 model: str = Form(""), n_frames: int = Form(8)):
    """One-click full evaluation: local D03/D04 plus every vision dimension.

    Per-dimension failures never persist and never abort the batch; the
    response carries every dimension with value=null for the failed ones.
    """
    if not get_video_path(video_id):
        raise HTTPException(status_code=404, detail="视频不存在")
    results = {}
    local_dims = [d["dim_id"] for d in DIMENSIONS
                  if d["dim_id"] in TEMPORAL_SIGNAL_DIMS]
    for dim_id, res in signal_metrics(
            get_video_path(video_id), local_dims).items():
        if res.get("value") is not None:
            insert_objective_score(video_id, dim_id, res, rater="signal_local",
                                   model="local_cpu", task_id="task_web")
        results[dim_id] = res

    base_url, api_key, model = _resolve_lmm(base_url, api_key, model)
    lmm_dims = [d["dim_id"] for d in DIMENSIONS
                if d["dim_id"] not in TEMPORAL_SIGNAL_DIMS]
    if not (base_url and api_key and model):
        for dim_id in lmm_dims:
            results[dim_id] = {"value": None, "confidence": None,
                               "note": "未配置视觉模型"}
        return results
    cfg = {"base_url": base_url, "api_key": api_key, "model": model,
           "n_frames": max(1, min(int(n_frames), 32)),
           "temperature": 0.0, "samplings": 1}
    for dim_id, res in auto_evaluate(video_id, lmm_dims, cfg,
                                     prompt_text).items():
        if res.get("value") is not None:
            insert_objective_score(video_id, dim_id, res, rater="lmm_" + model,
                                   model=model, task_id="task_web")
        results[dim_id] = res
    return results


class RecordIn(BaseModel):
    video_id: str


@server.post("/api/records")
def create_record(p: RecordIn):
    """Archive a snapshot of the latest objective score per dimension."""
    if not get_video_path(p.video_id):
        raise HTTPException(status_code=404, detail="视频不存在")
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT filename, model_tag FROM videos WHERE video_id=?",
              (p.video_id,))
    row = c.fetchone()
    c.execute("""SELECT scores FROM scores
                 WHERE video_id=? AND method='objective'
                 ORDER BY created_at DESC""", (p.video_id,))
    score_rows = c.fetchall()
    conn.close()
    snap = {}
    for (sc_json,) in score_rows:
        for dim_id, val in json.loads(sc_json).items():
            if (dim_id not in snap and isinstance(val, dict)
                    and val.get("value") is not None):
                snap[dim_id] = round(float(val["value"]), 2)
    scores = {d: snap.get(d) for d in DIM_IDS}
    rid = save_test_record(p.video_id, row[0] if row else p.video_id,
                           row[1] if row else "", scores)
    return {"ok": True, "record_id": rid, "scores": scores}


@server.get("/api/records")
def api_list_records():
    return list_test_records()


@server.delete("/api/records/{record_id}")
def api_delete_record(record_id: str):
    try:
        return delete_test_record(record_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="记录不存在") from None


# ---------------- PPT 评测（decks） ----------------

@server.get("/api/ppt/dimensions")
def ppt_dimensions():
    return [{
        "dim_id": d["dim_id"], "name": d["name"], "layer": d["layer"],
        "anchor_low": d["anchor_low"], "anchor_mid": d["anchor_mid"],
        "anchor_high": d["anchor_high"],
        "needs_render": bool(d.get("needs_render")),
        "needs_lmm": d["dim_id"] not in ppt_core.LOCAL_PPT_DIMS,
    } for d in ppt_core.PPT_DIMENSIONS]


@server.get("/api/ppt/renderer")
def ppt_renderer():
    return ppt_core.detect_renderer()


@server.post("/api/deck/upload")
async def deck_upload(file: UploadFile = File(...), tool_tag: str = Form(""),
                      prompt_text: str = Form("")):
    tmp_dir = tempfile.mkdtemp()
    try:
        tmp_path = os.path.join(tmp_dir, os.path.basename(file.filename or "deck.pptx"))
        written = 0
        with open(tmp_path, "wb") as tmp:
            while chunk := await file.read(UPLOAD_CHUNK_BYTES):
                written += len(chunk)
                if written > 200 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="文件超过上限 200MB")
                tmp.write(chunk)
        return add_deck(tmp_path, tool_tag.strip(), prompt_text.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@server.get("/api/decks")
def api_decks():
    return list_decks()


@server.delete("/api/deck/{deck_id}")
def api_delete_deck(deck_id: str):
    try:
        return delete_deck(deck_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="PPT 不存在") from None


@server.get("/api/deck/{deck_id}/slide/{index}.png")
def deck_slide(deck_id: str, index: int):
    slides_dir = deck_slides_dir(deck_id)
    if not slides_dir or not (1 <= index <= ppt_core.MAX_RENDER_SLIDES):
        raise HTTPException(status_code=404, detail="页码超出范围")
    path = os.path.join(slides_dir, f"slide-{index:02d}.png")
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="尚未渲染（需先运行含设计维度的评测）")
    return FileResponse(path, media_type="image/png")


def _deck_lmm_cfg(base_url, api_key, model):
    base_url, api_key, model = _resolve_lmm(base_url, api_key, model)
    return {"base_url": base_url, "api_key": api_key, "model": model,
            "temperature": 0.0}


def _deck_dims_result(deck_id, dims, prompt_text, lmm_cfg):
    return ppt_core.evaluate_deck(
        get_deck_path(deck_id), dims, lmm_cfg, prompt_text,
        slides_dir=os.path.join(DECKS_DIR, f"{deck_id}_slides"))


@server.post("/api/deck/evaluate/{dim_id}")
def deck_evaluate(dim_id: str, deck_id: str = Form(...),
                  prompt_text: str = Form(""), base_url: str = Form(""),
                  api_key: str = Form(""), model: str = Form("")):
    dim = next((d for d in ppt_core.PPT_DIMENSIONS
                if d["dim_id"] == dim_id), None)
    if not dim:
        raise HTTPException(status_code=404, detail="未知维度")
    if not get_deck_path(deck_id):
        raise HTTPException(status_code=404, detail="PPT 不存在")
    res = _deck_dims_result(deck_id, [dim], prompt_text,
                            _deck_lmm_cfg(base_url, api_key, model)).get(dim_id)
    if res is None or res.get("value") is None:
        note = res.get("note") if res else "EVALUATION_FAILED"
        raise HTTPException(status_code=502, detail=f"评测失败：{note}")
    if dim_id in ppt_core.LOCAL_PPT_DIMS:
        insert_deck_objective_score(deck_id, dim_id, res,
                                    rater="ppt_local", model="local_rules")
    else:
        insert_deck_objective_score(deck_id, dim_id, res,
                                    rater="lmm_" + model, model=model)
    return {"dim_id": dim_id, **res, "method": "objective"}


@server.post("/api/deck/evaluate-all")
def deck_evaluate_all(deck_id: str = Form(...), prompt_text: str = Form(""),
                      base_url: str = Form(""), api_key: str = Form(""),
                      model: str = Form("")):
    """One-click full deck evaluation; failed dims are skipped, not stored."""
    if not get_deck_path(deck_id):
        raise HTTPException(status_code=404, detail="PPT 不存在")
    dims = list(ppt_core.PPT_DIMENSIONS)
    results = _deck_dims_result(deck_id, dims, prompt_text,
                                _deck_lmm_cfg(base_url, api_key, model))
    for dim_id, res in results.items():
        if res.get("value") is None:
            continue
        if dim_id in ppt_core.LOCAL_PPT_DIMS:
            insert_deck_objective_score(deck_id, dim_id, res,
                                        rater="ppt_local", model="local_rules")
        else:
            insert_deck_objective_score(deck_id, dim_id, res,
                                        rater="lmm_" + model, model=model)
    return results


@server.get("/api/deck/{deck_id}/scores")
def api_deck_scores(deck_id: str):
    """Latest objective score per dimension for a deck (newest wins)."""
    if not get_deck_path(deck_id):
        raise HTTPException(status_code=404, detail="PPT 不存在")
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT dim_id, scores FROM deck_scores
                 WHERE deck_id=? AND method='objective'
                 ORDER BY created_at DESC""", (deck_id,))
    rows = c.fetchall()
    conn.close()
    out = {}
    for dim_id, sc_json in rows:
        if dim_id in out:
            continue
        sc = json.loads(sc_json)
        if isinstance(sc, dict) and sc.get("value") is not None:
            out[dim_id] = {"value": sc.get("value"),
                           "confidence": sc.get("confidence"),
                           "note": sc.get("note", ""),
                           "method": "objective"}
    return out


@server.get("/api/deck/dashboard")
def api_deck_dashboard():
    return deck_dashboard_data()


@server.get("/api/video/{video_id}/file")
def video_file(video_id: str):
    p = get_video_path(video_id)
    if not p:
        raise HTTPException(status_code=404, detail="视频不存在")
    return FileResponse(p)


@server.get("/api/dashboard")
def api_dashboard():
    """Aggregated leaderboards, MOS histogram and world-model sub-board."""
    return dashboard_data()


@server.delete("/api/video/{video_id}")
def api_delete_video(video_id: str):
    try:
        return delete_video(video_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="视频不存在") from None
    except PermissionError:
        raise HTTPException(
            status_code=409, detail="文件正在被使用，请关闭播放后重试") from None


def _resolve_lmm(base_url, api_key, model):
    """Fill missing LMM settings from the saved configuration.

    An api_key coming back from the masked UI field contains `*` and is never
    a usable secret, so it is discarded before falling back.
    """
    if api_key and "*" in api_key:
        api_key = ""
    if base_url and api_key and model:
        return base_url, api_key, model
    saved = load_config().get("lmm", {})
    return (base_url or saved.get("base_url", ""),
            api_key or saved.get("api_key", ""),
            model or saved.get("model", ""))


@server.get("/api/config/lmm")
def get_lmm_config():
    """Saved LMM settings, with the API Key replaced by a masked string."""
    return load_lmm_config_masked()


@server.post("/api/config/lmm")
def post_lmm_config(base_url: str = Form(""), model: str = Form(""),
                    api_key: str = Form("")):
    base_url = base_url.strip()
    model = model.strip()
    if not base_url or not model:
        raise HTTPException(status_code=400, detail="Base URL 与模型名称不能为空")
    return save_lmm_config(base_url, model, api_key.strip())


@server.post("/api/check-vision")
def check_vision(base_url: str = Form(""), api_key: str = Form(""),
                 model: str = Form("")):
    base_url, api_key, model = _resolve_lmm(base_url, api_key, model)
    if not (base_url and api_key and model):
        return {"has_vision": False, "missing": True}
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
        if res.get("value") is None:
            raise HTTPException(
                status_code=502,
                detail=f"评测失败：{res.get('note') or 'LOCAL_SIGNAL_FAILED'}")
        insert_objective_score(video_id, dim_id, res,
                               rater="signal_local", model="local_cpu",
                               task_id="task_web")
        return {"dim_id": dim_id, **res, "method": "objective"}

    base_url, api_key, model = _resolve_lmm(base_url, api_key, model)
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


class SubjectiveIn(BaseModel):
    video_id: str
    role: str = "user"          # user | expert
    rater_id: str = "anon"
    dims: dict = {}             # {dim_id: 0-10}
    gate: str = "na"            # technical | physical | semantic | na
    gates: dict = {}            # optional per-dimension low-score gates
    note: str = ""
    ab_choice: Optional[str] = None
    ab_vs: Optional[str] = None


@server.post("/api/score/subjective")
def post_subjective(p: SubjectiveIn):
    """Persist a human/expert rating (expert role => arbitration override)."""
    if p.role not in ("user", "expert"):
        raise HTTPException(status_code=400, detail="role 必须是 user 或 expert")
    if not p.rater_id.strip():
        raise HTTPException(status_code=400, detail="评测者 ID 不能为空")
    if not p.dims:
        raise HTTPException(status_code=400, detail="至少提交一个维度的评分")
    if not get_video_path(p.video_id):
        raise HTTPException(status_code=404, detail="视频不存在")
    try:
        detail = save_subjective(p.video_id, p.role, p.rater_id, p.dims,
                                 p.gate, p.note, p.ab_choice, p.ab_vs, p.gates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "detail": detail}


@server.get("/api/reliability")
def reliability():
    """Per-dimension inter-rater reliability: ICC(2,1) and Krippendorff's α."""
    out = []
    for d in DIMENSIONS:
        out.append({
            "dim_id": d["dim_id"], "name": d["name"],
            "icc": compute_icc_matrix(d["dim_id"]),
            "krippendorff_alpha": compute_krippendorff_alpha(d["dim_id"]),
        })
    return out


@server.get("/api/export/vbench")
def export_vbench_ep():
    """Regenerate and download the VBench-compatible leaderboard JSON."""
    path = export_vbench()
    return FileResponse(path, media_type="application/json",
                        filename="vbench_export.json")


def _report_port_busy(port):
    message = f"端口 {port} 已被占用，请关闭已有实例或用 VIDEOEVAL_PORT 指定其他端口"
    log.error(message)
    if getattr(sys, "frozen", False):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "AI 视频质量评测", 0x10)
        except Exception:
            pass


# Static front-end last so /api routes take precedence.
server.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")


def _start_tray(port):
    """Launch a system-tray icon for windowed (frozen) builds.

    Returns True on success. Imports are deferred so dev/console runs never
    require pystray/Pillow to be installed.
    """
    try:
        import pystray  # type: ignore[import-untyped]
        from PIL import Image  # type: ignore[import-untyped]
    except Exception as e:  # pragma: no cover - depends on optional deps
        # Never print() here: windowed builds have no stdout and print would
        # itself raise, killing the whole app during startup.
        log.warning("tray unavailable: %s", e)
        return False
    img = Image.new("RGB", (64, 64), (37, 99, 235))

    def open_browser(icon, item):
        webbrowser.open(f"http://127.0.0.1:{port}")

    def quit_app(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("打开浏览器", open_browser),
        pystray.MenuItem("退出", quit_app),
    )
    icon = pystray.Icon("VideoEvalWeb", img, "AI 视频质量评测", menu)
    threading.Thread(target=icon.run, daemon=True).start()
    return True


if __name__ == "__main__":
    if "--render-child" in sys.argv:
        # Isolated slide-rendering child: `server.py --render-child <pptx> <outdir>`.
        # COM requires a specific thread model, so it never runs inside uvicorn.
        i = sys.argv.index("--render-child")
        ppt_core.run_render_child(sys.argv[i + 1], sys.argv[i + 2])
        raise SystemExit(0)

    import urllib.request

    import uvicorn

    def own_app_on(candidate):
        """True when an instance of this app already serves on candidate."""
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{candidate}/api/health", timeout=1.5) as r:
                data = json.loads(r.read().decode("utf-8"))
            return bool(data.get("ok")) and "dimensions" in data
        except Exception:
            return False

    no_browser = os.environ.get("VIDEOEVAL_NO_BROWSER", "").lower() in {"1", "true", "yes"}
    strict = "VIDEOEVAL_PORT" in os.environ
    preferred = int(os.environ.get("VIDEOEVAL_PORT", "8765"))
    # Plain double-click must always work: attach to the running instance if
    # it is ours, otherwise fall forward to the next port. An explicit
    # VIDEOEVAL_PORT (automation) stays strict about its requested port.
    candidates = [preferred] if strict else [preferred] + list(range(8766, 8776))
    port = None
    for candidate in candidates:
        if is_port_free(candidate):
            port = candidate
            break
        if own_app_on(candidate):
            if not no_browser:
                webbrowser.open(f"http://127.0.0.1:{candidate}")
            log.info("app already running on port %s; exiting this launch", candidate)
            raise SystemExit(0)
    if port is None:
        _report_port_busy(preferred)
        raise SystemExit(2)
    if port != preferred:
        log.warning("preferred port %s busy; serving on %s", preferred, port)
    if getattr(sys, "frozen", False):
        # Windowed build: auto-open the browser so a double-click needs zero
        # further action (tray icons often hide in the Win11 overflow area,
        # which made the app look like it silently did nothing). The tray
        # stays available for re-opening and quitting.
        if not no_browser:
            _start_tray(port)
            threading.Timer(2.0, lambda: webbrowser.open(
                f"http://127.0.0.1:{port}")).start()
        uvicorn.run(server, host="127.0.0.1", port=port, log_config=None)
    else:
        if not no_browser:
            threading.Timer(1.5, lambda: webbrowser.open(
                f"http://127.0.0.1:{port}")).start()
        uvicorn.run(server, host="127.0.0.1", port=port)
