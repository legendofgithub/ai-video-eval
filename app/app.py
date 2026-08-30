# -*- coding: utf-8 -*-
"""
AI 生成视频质量评测工具 — 单文件 Gradio 应用 (v0.3)
本地优先 / 零基础设施 / 可 PyInstaller 打包分发
评测维度: 10 核心维 (D01-D10, 三层金字塔)
评测范式: LMM 自动(objective) + 人工 MOS(subjective) + 专家仲裁(expert_arbitration)
"""
import os, json, sqlite3, hashlib, base64, re, datetime, uuid

import numpy as np
import cv2
import gradio as gr
import plotly.graph_objects as go
import plotly.express as px
from openai import OpenAI

# ---------------- 路径 ----------------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
VIDEOS_DIR = os.path.join(DATA, "videos")
FRAMES_DIR = os.path.join(DATA, "frames")
DB = os.path.join(BASE, "evaluation.db")
CONFIG_PATH = os.path.join(BASE, "config.json")
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# ---------------- 10 维度配置 (与任务二 Schema 对齐) ----------------
DIMENSIONS = [
    {"dim_id": "D01", "name": "成像质量", "layer": "technical",
     "anchor_low": "明显噪点/模糊/压缩块", "anchor_mid": "基本清晰偶有瑕疵", "anchor_high": "通透清晰无伪影"},
    {"dim_id": "D02", "name": "美学质量", "layer": "technical",
     "anchor_low": "构图混乱/色调脏", "anchor_mid": "尚可", "anchor_high": "构图与光影专业"},
    {"dim_id": "D03", "name": "时序闪烁", "layer": "technical",
     "anchor_low": "持续闪烁/画面跳动", "anchor_mid": "偶发微闪", "anchor_high": "时序稳定无闪",
     "metric": "local_signal", "needs_temporal_signal": True},
    {"dim_id": "D04", "name": "运动平滑度", "layer": "technical",
     "anchor_low": "卡顿/突变/撕裂", "anchor_mid": "基本顺滑", "anchor_high": "运动自然连贯",
     "metric": "local_signal", "needs_temporal_signal": True},
    {"dim_id": "D05", "name": "主体一致性", "layer": "semantic",
     "anchor_low": "主体外观频繁变", "anchor_mid": "主体大体一致", "anchor_high": "全程主体稳定"},
    {"dim_id": "D06", "name": "背景一致性", "layer": "semantic",
     "anchor_low": "背景乱变/穿帮", "anchor_mid": "背景基本稳", "anchor_high": "背景连贯合理"},
    {"dim_id": "D07", "name": "文本-视频对齐", "layer": "semantic",
     "anchor_low": "与prompt严重不符", "anchor_mid": "部分符合", "anchor_high": "精准还原prompt"},
    {"dim_id": "D08", "name": "物理规律", "layer": "world_model",
     "anchor_low": "明显违重力/碰撞/浮力", "anchor_mid": "偶有轻微违和", "anchor_high": "符合物理规律"},
    {"dim_id": "D09", "name": "人体动作与结构", "layer": "world_model",
     "anchor_low": "骨骼/关节明显畸变", "anchor_mid": "轻微不自然", "anchor_high": "人体结构合理"},
    {"dim_id": "D10", "name": "常识推理", "layer": "world_model",
     "anchor_low": "违背常识/因果错乱", "anchor_mid": "基本合理", "anchor_high": "符合常识与因果"},
]
DIM_IDS = [d["dim_id"] for d in DIMENSIONS]
DIM_NAME = {d["dim_id"]: d["name"] for d in DIMENSIONS}
DEFAULT_SPEC_ID = "spec_default_10"
# 时序维度：自动评测默认走本地 CPU 信号指标，而非 LMM 静态抽帧（静态帧无法观测运动/闪烁）
TEMPORAL_SIGNAL_DIMS = {"D03", "D04"}

# ---------------- 配置 ----------------
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"lmm": {"provider": "ollama", "base_url": "http://localhost:11434/v1",
                    "api_key": "ollama", "model": "deepseek-vl2",
                    "n_frames": 8, "temperature": 0.0, "samplings": 1}}

def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ---------------- 数据库 ----------------
def get_conn():
    return sqlite3.connect(DB)

def init_db():
    conn = get_conn(); c = conn.cursor()
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
    # 默认 10 维配置
    c.execute("SELECT 1 FROM specs WHERE spec_id=?", (DEFAULT_SPEC_ID,))
    if not c.fetchone():
        c.execute("INSERT INTO specs VALUES (?,?,?,?,?)",
                  (DEFAULT_SPEC_ID, "Default 10-core (v0.3)", 10, "mixed", json.dumps(DIMENSIONS, ensure_ascii=False)))
    conn.commit(); conn.close()

def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def video_meta(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    dur = frames / fps if fps else 0
    return fps, frames, w, h, dur

def sample_frames(path, n=8, out_dir=None):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total == 0:
        cap.release(); return []
    idxs = [int(i * total / n) for i in range(n)]
    paths = []
    for i in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(i, total - 1))
        ok, frame = cap.read()
        if not ok:
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
            p = os.path.join(out_dir, f"f{i:04d}.jpg")
            # 用 imencode + 二进制写，避开 OpenCV 在 Windows 中文路径下 cv2.imwrite 静默失败
            ok_w, buf = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
            if ok_w:
                with open(p, "wb") as wf:
                    wf.write(buf.tobytes())
                paths.append(p)
    cap.release()
    return paths

def frame_to_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ---------------- LMM 自动评测 (OpenAI 兼容视觉接口) ----------------
def build_dim_prompt(dim, prompt_text=None):
    p = (f"你是 AI 视频质量评测专家。请对这段 AI 生成的视频在维度「{dim['name']}」({dim['dim_id']}, 层={dim['layer']}) 上打分。\n"
         f"0-10 分锚定：低分={dim['anchor_low']}；中分={dim['anchor_mid']}；高分={dim['anchor_high']}。\n")
    if dim["dim_id"] == "D07" and prompt_text:
        p += f"该视频的生成文本提示(prompt)是：{prompt_text}\n请判断视频是否精准还原该提示。\n"
    p += ("仅输出 JSON，格式：{\"value\": <0-10数字>, \"confidence\": <0-1数字>, \"note\": \"<简短理由或违规描述>\"}。"
          "不要输出任何其他文字。")
    return p

def score_one_dim(client, model, dim, frame_paths, prompt_text, temperature):
    content = [{"type": "text", "text": build_dim_prompt(dim, prompt_text)}]
    for fp in frame_paths:
        b64 = frame_to_b64(fp)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    try:
        resp = client.chat.completions.create(
            model=model, temperature=temperature,
            messages=[{"role": "user", "content": content}])
        txt = resp.choices[0].message.content
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            val = float(obj.get("value", -1)); 
            if 0 <= val <= 10:
                return {"value": round(val, 2),
                        "confidence": round(float(obj.get("confidence", 0.5)), 2),
                        "note": str(obj.get("note", ""))}
    except Exception as e:
        return {"value": None, "confidence": None, "note": f"LMM_ERROR: {e}"}
    return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}

# ---------------- 本地 CPU 信号指标 (D03 时序闪烁 / D04 运动平滑度) ----------------
# 方案 A：纯 cv2/numpy 实现，零成本、零 API，且能真实观测帧间时序变化
# （LMM 静态抽帧无法判断运动/闪烁，故这两维改走本地信号）
def _sample_gray_frames(path, n=24, size=(320, 180)):
    """均匀抽帧并转灰度缩放，返回 numpy 数组列表（不落盘，避开中文路径问题）"""
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
    """D03 时序闪烁：以高频边缘(Laplacian)的时序不稳定性为主，帧差抖动为辅。
    返回 0-10，越高越稳定；含启发式映射说明。"""
    n = len(grays)
    if n < 2:
        return None, "帧数不足"
    # 每帧高频细节量（拉普拉斯方差）：闪烁→该值帧间剧烈跳动
    lap = np.array([cv2.Laplacian(g, cv2.CV_64F).var() for g in grays])
    lap_cv = lap.std() / (lap.mean() + 1e-6)          # 边缘噪声的时序变异系数
    # 帧间绝对差抖动
    diffs = np.array([np.abs(grays[i].astype(float) - grays[i - 1].astype(float)).mean()
                      for i in range(1, n)])
    diff_cv = diffs.std() / (diffs.mean() + 1e-6)     # 帧差时序变异系数
    flicker_idx = 0.6 * lap_cv + 0.4 * diff_cv        # 综合闪烁指数（越大越闪）
    score = float(np.clip(10 * np.exp(-flicker_idx * 0.8), 0, 10))
    return round(score, 2), f"本地信号: 闪烁指数={flicker_idx:.3f}(边缘CV={lap_cv:.3f},帧差CV={diff_cv:.3f})"

def _motion_smooth_score(grays):
    """D04 运动平滑度：Farneback 稠密光流估计帧间运动量，以运动量序列的突变(jerk)衡量顺滑度。
    返回 0-10，越高越顺滑；归一化到平均运动量，静态/动态均可比。"""
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
    jerk = np.abs(np.diff(mags))                       # 运动量逐帧跳变（卡顿/瞬移）
    mean_motion = mags.mean()
    norm_jerk = jerk.mean() / (mean_motion + 1e-6)     # 相对运动量归一，去分辨率/速度影响
    score = float(np.clip(10 * np.exp(-norm_jerk * 0.5), 0, 10))
    return round(score, 2), f"本地信号: 归一化运动突变={norm_jerk:.3f}(均值光流={mean_motion:.3f})"

def signal_metrics(video_path, dims):
    """对 D03/D04 计算本地信号指标；dims 仅取其中的子集。返回 {dim_id: {value,confidence,note}}"""
    grays = _sample_gray_frames(video_path, n=24)
    out = {}
    if "D03" in dims:
        v, note = _flicker_score(grays)
        out["D03"] = {"value": v, "confidence": 0.9 if v is not None else None, "note": note}
    if "D04" in dims:
        v, note = _motion_smooth_score(grays)
        out["D04"] = {"value": v, "confidence": 0.9 if v is not None else None, "note": note}
    return out

def auto_evaluate(video_id, dims, model_cfg=None, prompt_text=None):
    """对指定维度调用 LMM 打分，返回 {dim_id: {value,confidence,note}}"""
    """对指定维度打分：D03/D04 走本地信号指标；其余走 LMM。
    返回 {dim_id: {value,confidence,note}}。LMM 不可用时本地维度仍正常返回。"""
    results = {}
    # --- 本地信号维度（无需 API，优先计算）---
    local_dims = [d for d in dims if d in TEMPORAL_SIGNAL_DIMS]
    if local_dims:
        vpath = get_video_path(video_id)
        if vpath:
            results.update(signal_metrics(vpath, local_dims))
        else:
            for d in local_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_VIDEO_FILE"}
    # --- LMM 维度 ---
    lmm_dims = [d for d in dims if d not in TEMPORAL_SIGNAL_DIMS]
    if not lmm_dims:
        return results
    try:
        cfg = load_config()
        lmm = cfg["lmm"]
        client = OpenAI(base_url=lmm["base_url"], api_key=lmm["api_key"])
        vpath = get_video_path(video_id)
        if not vpath:
            for d in lmm_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_VIDEO_FILE"}
            return results
        frame_paths = sample_frames(vpath, lmm["n_frames"], os.path.join(FRAMES_DIR, video_id))
        if not frame_paths:
            for d in lmm_dims:
                results[d] = {"value": None, "confidence": None, "note": "NO_FRAMES"}
            return results
        for dim_id in lmm_dims:
            dim = next(d for d in DIMENSIONS if d["dim_id"] == dim_id)
            agg = None
            for _ in range(max(1, lmm.get("samplings", 1))):
                r = score_one_dim(client, lmm["model"], dim, frame_paths, prompt_text, lmm["temperature"])
                if r["value"] is None:
                    results[dim_id] = r   # 该维失败，记录错误，不阻断其他维
                    break
                if agg is None:
                    agg = {"value": [], "confidence": [], "note": r["note"]}
                agg["value"].append(r["value"]); agg["confidence"].append(r["confidence"])
            else:
                results[dim_id] = {"value": round(float(np.mean(agg["value"])), 2),
                                   "confidence": round(float(np.mean(agg["confidence"])), 2),
                                   "note": agg["note"]}
    except Exception as e:
        for d in lmm_dims:
            if d not in results:
                results[d] = {"value": None, "confidence": None, "note": f"LMM_UNAVAILABLE: {e}"}
    return results

# ---------------- ICC(2,1) 一致性 ----------------
def compute_icc_matrix(dim_id):
    """跨所有视频、对所有标注员计算该维度的 ICC(2,1)"""
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, rater_id, scores FROM scores
                 WHERE method='subjective' AND is_valid=1""")
    rows = c.fetchall(); conn.close()
    # 构建 video x rater 矩阵
    data = {}
    raters = set()
    for vid, rater, sc_json in rows:
        sc = json.loads(sc_json)
        if dim_id in sc and sc[dim_id].get("value") is not None:
            data.setdefault(vid, {})[rater] = float(sc[dim_id]["value"])
            raters.add(rater)
    raters = sorted(raters)
    if len(raters) < 2:
        return None
    matrix = [data[vid] for vid in data if all(r in data[vid] for r in raters)]
    if len(matrix) < 2:
        return None
    M = np.array([[row[r] for r in raters] for row in matrix])  # n x k
    n, k = M.shape
    grand = M.mean()
    col_means = M.mean(axis=0)
    row_means = M.mean(axis=1)
    BMS = k * np.sum((row_means - grand) ** 2) / (n - 1)
    WMS = np.sum((M - row_means[:, None] - col_means[None, :] + grand) ** 2) / (n * (k - 1))
    if BMS + (k - 1) * WMS == 0:
        return None
    icc = (BMS - WMS) / (BMS + (k - 1) * WMS)
    return round(float(icc), 3)

# ---------------- 业务操作 ----------------
def add_video(file_obj, url, prompt_text, model_tag):
    if file_obj is not None:
        src = file_obj.name if hasattr(file_obj, "name") else file_obj
        vid = uuid.uuid4().hex[:8]
        ext = os.path.splitext(src)[1] or ".mp4"
        dst = os.path.join(VIDEOS_DIR, f"{vid}{ext}")
        # Gradio 临时文件拷贝
        import shutil
        shutil.copy(src, dst)
        h = md5_file(dst)
        fps, frames, w, hgt, dur = video_meta(dst)
        thumb_dir = os.path.join(FRAMES_DIR, vid)
        sample_frames(dst, 1, thumb_dir)
        thumb = os.path.join(thumb_dir, "f0000.jpg") if os.path.exists(os.path.join(thumb_dir, "f0000.jpg")) else None
        size_mb = round(os.path.getsize(dst) / 1e6, 2)
        conn = get_conn(); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (vid, os.path.basename(src), "upload", None, h, round(dur, 2), int(fps),
                   f"{w}x{hgt}", size_mb, prompt_text, model_tag,
                   datetime.datetime.now().isoformat(), thumb))
        conn.commit(); conn.close()
        # 重命名为 video_id.mp4 统一
        final = os.path.join(VIDEOS_DIR, f"{vid}.mp4")
        if dst != final:
            shutil.move(dst, final)
        return vid, f"已入库 video_id={vid} ({w}x{hgt}, {round(dur,2)}s)"
    return None, "未提供视频文件"

def video_choices():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT video_id, filename, model_tag FROM videos ORDER BY created_at DESC")
    rows = c.fetchall(); conn.close()
    return [(f"{r[0]} | {r[1]} | {r[2] or '-'}", r[0]) for r in rows]

def save_subjective(video_id, role, rater_id, dims_vals, gate, note_text, ab_choice, ab_vs):
    """保存人工/专家评分。gate: technical/physical/semantic/na；is_valid 依门控判断"""
    scores = {}
    for dim_id, v in dims_vals.items():
        if v is not None:
            scores[dim_id] = {"value": float(v), "confidence": None, "note": ""}
    # 高层维度(D08-D10)若低分且 gate!=physical -> 标 invalid
    is_valid = 1
    for dim_id in ("D08", "D09", "D10"):
        if dim_id in scores and scores[dim_id]["value"] <= 4 and gate != "physical":
            is_valid = 0
    for dim_id in ("D01", "D02", "D03", "D04"):
        if dim_id in scores and scores[dim_id]["value"] <= 4 and gate == "physical":
            is_valid = 0  # 技术维度误记为物理 -> 无效
    method = "expert_arbitration" if role == "expert" else "subjective"
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
              (uuid.uuid4().hex[:10], "task_manual", video_id, DEFAULT_SPEC_ID,
               rater_id, role, method, None, json.dumps(scores, ensure_ascii=False),
               json.dumps({"vs_video_id": ab_vs, "choice": ab_choice, "reason": note_text}) if ab_choice else None,
               is_valid, datetime.datetime.now().isoformat()))
    conn.commit(); conn.close()
    return f"已保存({method}, is_valid={is_valid})"

def get_video_path(video_id):
    for ext in (".mp4", ".webm", ".mov"):
        p = os.path.join(VIDEOS_DIR, f"{video_id}{ext}")
        if os.path.exists(p):
            return p
    # 退而求其次按文件名前缀
    for f in os.listdir(VIDEOS_DIR):
        if f.startswith(video_id):
            return os.path.join(VIDEOS_DIR, f)
    return None

# ---------------- 可视化 ----------------
def _human_score_rows():
    """每个视频的有效人工分：优先专家仲裁(expert_arbitration)，否则 subjective(is_valid=1) 取均值。
    返回 list of (video_id, model_tag, scores_dict)。专家仲裁真正覆盖该视频的主观分。"""
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT s.video_id, v.model_tag, s.method, s.scores, s.is_valid
                 FROM scores s JOIN videos v ON v.video_id=s.video_id""")
    rows = c.fetchall(); conn.close()
    by_vid = {}
    for vid, tag, method, sc_json, is_valid in rows:
        sc = json.loads(sc_json)
        d = by_vid.setdefault(vid, {"model_tag": tag, "expert": None, "sub": []})
        if method == "expert_arbitration":
            d["expert"] = sc
        elif method == "subjective" and is_valid == 1:
            d["sub"].append(sc)
    out = []
    for vid, d in by_vid.items():
        if d["expert"] is not None:
            out.append((vid, d["model_tag"], d["expert"]))
        elif d["sub"]:
            merged = {}
            for sc in d["sub"]:
                for dim, v in sc.items():
                    if isinstance(v, dict) and v.get("value") is not None:
                        merged.setdefault(dim, []).append(v["value"])
            merged = {dim: round(float(np.mean(vals)), 2) for dim, vals in merged.items()}
            out.append((vid, d["model_tag"], merged))
    return out

def _dim_value(sc, dim):
    """从 scores 行解析某维度数值（兼容 {value:..} 与裸 float 两种存储）"""
    v = sc.get(dim)
    if isinstance(v, dict):
        return v.get("value")
    return v

def radar_fig(video_id):
    """雷达图：机器客观分(LMM+本地信号) 与 人工/专家分 两条独立 trace，不混算。"""
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT method, scores FROM scores WHERE video_id=?", (video_id,))
    rows = c.fetchall(); conn.close()
    obj = {d: [] for d in DIM_IDS}
    for method, sc_json in rows:
        if method != "objective":
            continue
        sc = json.loads(sc_json)
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                obj[d].append(val)
    # 人工/专家分（专家仲裁覆盖）
    human_map = {vid: sc for vid, tag, sc in _human_score_rows()}
    hsc = human_map.get(video_id, {})
    obj_vals = [round(float(np.mean(obj[d])), 2) if obj[d] else 0 for d in DIM_IDS]
    human_vals = [_dim_value(hsc, d) if _dim_value(hsc, d) is not None else 0 for d in DIM_IDS]
    fig = go.Figure()
    if any(obj_vals):
        fig.add_trace(go.Scatterpolar(r=obj_vals + [obj_vals[0]], theta=DIM_IDS + [DIM_IDS[0]],
                                      fill="toself", name="机器客观分(LMM+本地信号)"))
    if any(human_vals):
        fig.add_trace(go.Scatterpolar(r=human_vals + [human_vals[0]], theta=DIM_IDS + [DIM_IDS[0]],
                                      fill="toself", name="人工/专家分(MOS)"))
    if not fig.data:
        fig.add_trace(go.Scatterpolar(r=[0] * 11, theta=DIM_IDS + [DIM_IDS[0]], name="暂无数据"))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
                      title=f"10 维雷达图 — {video_id}（客观 vs 人工，已区分）")
    return fig

def comparison_fig():
    """各模型按维度均值对比（人工/专家有效分，专家仲裁覆盖主观分）"""
    data = _human_score_rows()
    model_dims = {}
    for vid, tag, sc in data:
        if not tag:
            continue
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                model_dims.setdefault(tag, {}).setdefault(d, []).append(float(val))
    if not model_dims:
        return go.Figure()
    models = list(model_dims.keys())
    fig = go.Figure()
    for d in DIM_IDS:
        ys = [round(float(np.mean(model_dims[m][d])), 2) if d in model_dims[m] else 0 for m in models]
        fig.add_trace(go.Bar(x=models, y=ys, name=DIM_NAME[d]))
    fig.update_layout(barmode="group", title="各模型按维度均值对比(人工/专家分)", yaxis_range=[0, 10])
    return fig

def icc_table():
    res = []
    for d in DIM_IDS:
        icc = compute_icc_matrix(d)
        res.append({"维度": f"{d} {DIM_NAME[d]}", "ICC(2,1)": icc if icc is not None else "样本不足",
                    "预警": "⚠️<0.6" if (icc is not None and icc < 0.6) else "OK"})
    return res

def export_vbench():
    data = _human_score_rows()
    model_dims = {}
    for vid, tag, sc in data:
        if not tag:
            continue
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                model_dims.setdefault(tag, {}).setdefault(d, []).append(float(val))
    leaderboard = []
    for tag, dd in model_dims.items():
        mean_scores = {d: round(float(np.mean(dd[d])), 2) if d in dd else None for d in DIM_IDS}
        def _lm(keys):
            lst = [mean_scores[x] for x in keys if mean_scores[x] is not None]
            return float(np.mean(lst)) if lst else 0.0
        layer_means = {
            "technical": _lm(("D01", "D02", "D03", "D04")),
            "semantic": _lm(("D05", "D06", "D07")),
            "world_model": _lm(("D08", "D09", "D10")),
        }
        leaderboard.append({"model_tag": tag, "mean_scores": mean_scores,
                            "layer_means": {k: round(float(v), 2) for k, v in layer_means.items()}})
    out = {"export_version": "vbench_compat_1.0", "spec_id": DEFAULT_SPEC_ID,
           "mos_scale": 10, "leaderboard": leaderboard}
    out_path = os.path.join(BASE, "vbench_export.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out_path

# =================== Gradio UI ===================
init_db()
with gr.Blocks(title="AI 视频质量评测工具") as app:
    gr.Markdown("# AI 生成视频质量评测工具 (v0.3)\n本地自用 · 10 维 · LMM 自动 + 人工 MOS + 专家仲裁")

    with gr.Tab("① 上传与任务"):
        with gr.Row():
            up_file = gr.Video(label="上传视频 (mp4/webm/mov)")
            with gr.Column():
                up_url = gr.Textbox(label="或填写视频 URL (公开直链)")
                up_prompt = gr.Textbox(label="生成提示 prompt (D07 必需)")
                up_model = gr.Textbox(label="生成模型/版本标识 (如 self_test_v2)")
                up_btn = gr.Button("入库")
                up_out = gr.Textbox(label="结果")
        up_btn.click(add_video, [up_file, up_url, up_prompt, up_model], up_out)

    with gr.Tab("② LMM 自动评测"):
        ae_vid = gr.Dropdown(label="选择视频", choices=video_choices())
        ae_dims = gr.CheckboxGroup(label="评测维度", choices=DIM_IDS, value=DIM_IDS)
        ae_btn = gr.Button("运行自动打分")
        ae_out = gr.JSON(label="客观分结果")
        def run_ae(vid, dims):
            if not vid:
                return {"error": "请先选择视频"}
            conn = get_conn(); c = conn.cursor()
            c.execute("SELECT prompt_text FROM videos WHERE video_id=?", (vid,))
            r = c.fetchone(); conn.close()
            res = auto_evaluate(vid, dims, load_config()["lmm"], r[0] if r else None)
            # 落库 objective
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:10], "task_auto", vid, DEFAULT_SPEC_ID,
                       "lmm_" + load_config()["lmm"]["model"], "lmm_auto", "objective",
                       load_config()["lmm"]["model"], json.dumps(res, ensure_ascii=False), None, 1,
                       datetime.datetime.now().isoformat()))
            conn.commit(); conn.close()
            return res
        ae_btn.click(run_ae, [ae_vid, ae_dims], ae_out)
        gr.Markdown("说明：D03 时序闪烁、D04 运动平滑度 **自动走本地 CPU 信号指标（光流/帧差分，零成本、无需 API）**；"
                    "其余 8 维走 LMM 视觉模型（需在「⑥ 设置」填入视觉 API，如 DeepSeek-V4-vision / GPT-4o / Gemini / 本地 Ollama+DeepSeek-VL2）。"
                    "即使无 API Key，本地信号维度仍可正常出分。")

    with gr.Tab("③ 人工标注台"):
        an_vid = gr.Dropdown(label="选择视频", choices=video_choices())
        an_player = gr.Video(label="播放 (可慢放/逐帧)")
        an_vid.change(lambda v: get_video_path(v), an_vid, an_player)
        an_sliders = {}
        with gr.Row():
            for d in DIMENSIONS:
                an_sliders[d["dim_id"]] = gr.Slider(0, 10, step=0.5, label=f"{d['dim_id']} {d['name']}\n({d['layer']})")
        an_gate = gr.Radio(["technical", "physical", "semantic", "na"], label="低分归因门控 (技术失真/物理常识/语义不符/无)", value="na")
        an_rater = gr.Textbox(label="标注员 ID", value="u_001")
        an_note = gr.Textbox(label="备注 / 高层维违规note (类型@时间戳;置信度)")
        an_ab_choice = gr.Radio(["A", "B", "tie", ""], label="A-B 配对偏好 (可选)")
        an_ab_vs = gr.Dropdown(label="对比视频 (A-B)", choices=video_choices(), value=None)
        an_btn = gr.Button("提交评分")
        an_out = gr.Textbox(label="结果")
        def collect_and_save(vid, *vals):
            dims_vals = {DIM_IDS[i]: v for i, v in enumerate(vals[:-5])}
            gate = vals[-5]; rater = vals[-4]; note = vals[-3]; ab_c = vals[-2]; ab_vs = vals[-1]
            return save_subjective(vid, "user", rater, dims_vals, gate, note, ab_c, ab_vs)
        an_btn.click(collect_and_save,
                     [an_vid] + [an_sliders[d] for d in DIM_IDS] + [an_gate, an_rater, an_note, an_ab_choice, an_ab_vs],
                     an_out)

    with gr.Tab("④ 专家仲裁"):
        ex_vid = gr.Dropdown(label="选择争议视频", choices=video_choices())
        ex_player = gr.Video(label="播放")
        ex_vid.change(lambda v: get_video_path(v), ex_vid, ex_player)
        ex_sliders = {}
        with gr.Row():
            for d in DIMENSIONS:
                ex_sliders[d["dim_id"]] = gr.Slider(0, 10, step=0.5, label=f"{d['dim_id']} {d['name']}")
        ex_rater = gr.Textbox(label="专家 ID", value="exp_tony")
        ex_btn = gr.Button("提交仲裁 (覆盖)")
        ex_out = gr.Textbox(label="结果")
        def ex_save(vid, *vals):
            dims_vals = {DIM_IDS[i]: v for i, v in enumerate(vals[:-1])}
            return save_subjective(vid, "expert", vals[-1], dims_vals, "na", "", "", "")
        ex_btn.click(ex_save, [ex_vid] + [ex_sliders[d] for d in DIM_IDS] + [ex_rater], ex_out)

    with gr.Tab("⑤ 可视化看板"):
        vb_vid = gr.Dropdown(label="雷达图视频", choices=video_choices())
        vb_radar = gr.Plot()
        vb_vid.change(radar_fig, vb_vid, vb_radar)
        vb_bar = gr.Plot(label="模型对比柱状图")
        vb_bar_btn = gr.Button("生成模型对比")
        vb_bar_btn.click(comparison_fig, None, vb_bar)
        vb_icc = gr.DataFrame(icc_table(), label="ICC(2,1) 一致性 (主观有效分)")
        vb_icc_btn = gr.Button("刷新 ICC")
        vb_icc_btn.click(icc_table, None, vb_icc)
        vb_exp = gr.Button("导出 VBench 兼容 JSON")
        vb_exp_out = gr.Textbox(label="导出路径")
        vb_exp.click(export_vbench, None, vb_exp_out)

    with gr.Tab("⑥ 设置 (LMM API)"):
        st_provider = gr.Textbox(label="provider")
        st_base = gr.Textbox(label="base_url (OpenAI 兼容)")
        st_key = gr.Textbox(label="api_key", type="password")
        st_model = gr.Textbox(label="model (如 deepseek-vl2 / gpt-4o / gemini-2.0-flash)")
        st_nf = gr.Number(label="抽帧数", value=8)
        st_btn = gr.Button("保存设置")
        st_out = gr.Textbox(label="结果")
        def load_to_ui():
            c = load_config()["lmm"]
            return c["provider"], c["base_url"], c["api_key"], c["model"], c["n_frames"]
        def save_ui(p, b, k, m, n):
            cfg = load_config()
            cfg["lmm"] = {"provider": p, "base_url": b, "api_key": k, "model": m,
                          "n_frames": int(n), "temperature": 0.0, "samplings": 1}
            save_config(cfg)
            return "已保存"
        app.load(load_to_ui, None, [st_provider, st_base, st_key, st_model, st_nf])
        st_btn.click(save_ui, [st_provider, st_base, st_key, st_model, st_nf], st_out)

if __name__ == "__main__":
    app.launch()
