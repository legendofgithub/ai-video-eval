# -*- coding: utf-8 -*-
"""SQLite storage and video lifecycle operations (single source of truth)."""
import datetime
import json
import math
import os
import shutil
import sqlite3
import sys
import uuid

from .dimensions import DIMENSIONS, DIM_IDS, DEFAULT_SPEC_ID
from .logger import get_logger
from .media import md5_file, video_meta, validate_video, sample_frames

log = get_logger("videoeval.storage")

def _app_base():
    """Frozen exe keeps persistent data next to the executable."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


BASE = _app_base()
DATA = os.path.join(BASE, "data")
VIDEOS_DIR = os.path.join(DATA, "videos")
FRAMES_DIR = os.path.join(DATA, "frames")
DB = os.path.join(BASE, "evaluation.db")
CONFIG_PATH = os.path.join(BASE, "config.json")

os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

MAX_UPLOAD_MB = 500


def get_conn():
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db():
    conn = get_conn(); c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY, filename TEXT, source TEXT, url TEXT,
        file_hash TEXT, duration_sec REAL, fps INT, resolution TEXT,
        file_size_mb REAL, prompt_text TEXT, model_tag TEXT,
        created_at TEXT, thumbnail_path TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS specs (
        spec_id TEXT PRIMARY KEY, name TEXT, mos_scale INT, mode TEXT, dimensions TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        task_id TEXT PRIMARY KEY, name TEXT, spec_id TEXT, mode TEXT, status TEXT, created_at TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS scores (
        score_id TEXT PRIMARY KEY, task_id TEXT, video_id TEXT, spec_id TEXT,
        rater_id TEXT, role TEXT, method TEXT, model TEXT,
        scores TEXT, ab_preference TEXT, is_valid INTEGER, created_at TEXT)""")
    c.execute("SELECT 1 FROM specs WHERE spec_id=?", (DEFAULT_SPEC_ID,))
    if not c.fetchone():
        c.execute("INSERT INTO specs VALUES (?,?,?,?,?)",
                  (DEFAULT_SPEC_ID, "Default 10-core (v0.3)", 10, "mixed",
                   json.dumps(DIMENSIONS, ensure_ascii=False)))
    conn.commit(); conn.close()


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lmm": {"provider": "ollama", "base_url": "http://localhost:11434/v1",
                    "api_key": "", "model": "deepseek-vl2",
                    "n_frames": 8, "temperature": 0.0, "samplings": 1}}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_video_path(video_id):
    def safe_path(filename):
        root = os.path.abspath(VIDEOS_DIR)
        path = os.path.abspath(os.path.join(root, filename))
        relative = os.path.relpath(path, root)
        if relative == os.curdir or relative.startswith(f"..{os.sep}") or os.path.isabs(relative):
            return None
        return path if os.path.isfile(path) else None

    for ext in (".mp4", ".webm", ".mov"):
        p = safe_path(f"{video_id}{ext}")
        if p:
            return p
    for f in os.listdir(VIDEOS_DIR):
        if f.startswith(video_id):
            p = safe_path(f)
            if p:
                return p
    return None


def add_video(src, prompt_text="", model_tag="", max_mb=MAX_UPLOAD_MB):
    """Copy a video file into the store and register it.

    Raises ValueError for invalid/oversized files; duplicates resolve to the
    existing record. Returns a metadata dict.
    """
    ext = os.path.splitext(src)[1].lower() or ".mp4"
    if ext not in (".mp4", ".webm", ".mov"):
        raise ValueError("仅支持 mp4/webm/mov")
    size_mb = os.path.getsize(src) / 1e6
    if size_mb > max_mb:
        raise ValueError(f"文件超过上限 {max_mb}MB")
    if not validate_video(src):
        log.warning("upload rejected (invalid video): %s", src)
        raise ValueError("无法读取视频或分辨率无效")

    # Hash first so a duplicate is never copied (cheaper + avoids leaving a
    # stray file when the dedup path would otherwise delete it).
    h = md5_file(src)
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, filename, duration_sec, fps, resolution,
                        file_size_mb, prompt_text, model_tag
                 FROM videos WHERE file_hash=?""", (h,))
    dup = c.fetchone()
    if dup:
        conn.close()
        log.info("upload duplicate resolved: %s -> %s", src, dup[0])
        return {
            "video_id": dup[0], "duplicate": True, "filename": dup[1],
            "duration_sec": dup[2], "fps": dup[3], "resolution": dup[4],
            "file_size_mb": dup[5], "prompt_text": dup[6],
            "model_tag": dup[7],
        }

    vid = uuid.uuid4().hex[:8]
    dst = os.path.join(VIDEOS_DIR, f"{vid}{ext}")
    shutil.copy(src, dst)

    fps, frames, w, hgt, dur = video_meta(dst)
    thumb_dir = os.path.join(FRAMES_DIR, vid)
    sample_frames(dst, 1, thumb_dir)
    thumb = os.path.join(thumb_dir, "f0000.jpg") if os.path.exists(
        os.path.join(thumb_dir, "f0000.jpg")) else None
    c.execute("INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (vid, os.path.basename(src), "upload", None, h,
               round(dur, 2), int(fps or 24), f"{w}x{hgt}",
               round(size_mb, 2), prompt_text, model_tag,
               datetime.datetime.now().isoformat(), thumb))
    conn.commit(); conn.close()
    log.info("video added: id=%s file=%s res=%s", vid, os.path.basename(src),
             f"{w}x{hgt}")
    return {
        "video_id": vid, "duplicate": False, "filename": os.path.basename(src),
        "duration_sec": round(dur, 2), "fps": int(fps or 24),
        "resolution": f"{w}x{hgt}", "file_size_mb": round(size_mb, 2),
        "prompt_text": prompt_text, "model_tag": model_tag,
    }


def delete_video(video_id):
    """Delete files first, records second.

    If the file is locked (e.g. still playing in a browser), PermissionError
    propagates before any DB write, so records stay intact.
    """
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,))
    if not c.fetchone():
        conn.close()
        raise LookupError("视频不存在")

    vpath = get_video_path(video_id)
    if vpath:
        os.remove(vpath)  # may raise PermissionError -> abort, records intact
    shutil.rmtree(os.path.join(FRAMES_DIR, video_id), ignore_errors=True)

    c.execute("DELETE FROM scores WHERE video_id=?", (video_id,))
    c.execute("DELETE FROM videos WHERE video_id=?", (video_id,))
    conn.commit(); conn.close()
    log.info("video deleted: id=%s", video_id)
    return {"ok": True, "deleted": video_id}


def list_videos(limit=20):
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, filename, model_tag, resolution,
                        duration_sec, created_at FROM videos
                 ORDER BY created_at DESC LIMIT ?""", (limit,))
    rows = c.fetchall(); conn.close()
    return [{"video_id": r[0], "filename": r[1], "model_tag": r[2],
             "resolution": r[3], "duration_sec": r[4], "created_at": r[5],
            }
            for r in rows]


def insert_objective_score(video_id, dim_id, res, rater, model,
                           task_id="task_auto"):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (uuid.uuid4().hex[:10], task_id, video_id, DEFAULT_SPEC_ID,
               rater, "lmm_auto", "objective", model,
               json.dumps({dim_id: res}, ensure_ascii=False), None, 1,
               datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()


def save_subjective(video_id, role, rater_id, dims_vals, gate, note_text,
                    ab_choice, ab_vs, dim_gates=None):
    """Save a human/expert rating with per-dimension low-score gates.

    ``gate`` remains the compatibility fallback. Low scores must select the
    gate matching their dimension layer; scores are grouped into valid and
    invalid rows so one bad low-score classification never invalidates other
    dimensions in reliability statistics.
    """
    dim_gates = dim_gates or {}
    if gate not in {"technical", "physical", "semantic", "na"}:
        raise ValueError("未知低分门控类型")
    if not str(rater_id).strip():
        raise ValueError("评测者 ID 不能为空")
    if not dims_vals:
        raise ValueError("至少提交一个维度的评分")
    unknown = set(dims_vals) - set(DIM_IDS)
    if unknown:
        raise ValueError(f"未知评测维度: {', '.join(sorted(unknown))}")
    unknown_gates = set(dim_gates) - set(DIM_IDS)
    if unknown_gates:
        raise ValueError(f"未知低分门控维度: {', '.join(sorted(unknown_gates))}")
    if any(g not in {"technical", "physical", "semantic", "na"}
           for g in dim_gates.values()):
        raise ValueError("未知低分门控类型")
    scores = {}
    valid_by_dim = {}
    expected_gate = {
        "technical": "technical",
        "semantic": "semantic",
        "world_model": "physical",
    }
    for dim_id, v in dims_vals.items():
        if v is not None:
            value = float(v)
            if not math.isfinite(value) or not 0 <= value <= 10:
                raise ValueError("评分必须在 0-10 之间")
            scores[dim_id] = {
                "value": value,
                "confidence": None,
                "note": str(note_text or "") if value <= 4 else "",
            }
            layer = next(d["layer"] for d in DIMENSIONS if d["dim_id"] == dim_id)
            selected_gate = dim_gates.get(dim_id, gate)
            valid_by_dim[dim_id] = (
                value > 4 or selected_gate == expected_gate[layer]
            )
    if not scores:
        raise ValueError("至少提交一个有效评分")
    method = "expert_arbitration" if role == "expert" else "subjective"
    conn = get_conn(); c = conn.cursor()
    first_row = True
    for is_valid in (1, 0):
        group = {dim: score for dim, score in scores.items()
                 if valid_by_dim[dim] == bool(is_valid)}
        if not group:
            continue
        c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex[:10], "task_manual", video_id, DEFAULT_SPEC_ID,
                   rater_id, role, method, None,
                   json.dumps(group, ensure_ascii=False),
                   json.dumps({"vs_video_id": ab_vs, "choice": ab_choice,
                               "reason": note_text})
                   if first_row and ab_choice else None,
                   is_valid, datetime.datetime.now().isoformat()))
        first_row = False
    conn.commit(); conn.close()
    valid_count = sum(valid_by_dim.values())
    return f"已保存({method}, 有效维度={valid_count}/{len(scores)})"
