# -*- coding: utf-8 -*-
"""真实测试：用 DeepSeek 官方视觉 API (deepseek-v4-flash-vision-exp) 评测测试用例视频。"""
import os, json, shutil, datetime, uuid, tempfile
import sys
import cv2
import app
from openai import OpenAI

SRC = r"F:\AI\codex project\AI视频评测\测试用例\华清普智孵化器广告.mp4"
VID = "huaqing_ad"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-flash-vision-exp"
N_FRAMES = 4
PROMPT_TEXT = "华清普智孵化器广告"

if not API_KEY:
    print("请先设置环境变量 DEEPSEEK_API_KEY（key 不再写入代码）")
    sys.exit(1)

# 1) 备份并切换 config 到 DeepSeek vision
backup = json.loads(json.dumps(app.load_config()))
cfg = app.load_config()
cfg["lmm"] = {"provider": "deepseek", "base_url": BASE_URL, "api_key": API_KEY,
             "model": MODEL, "n_frames": N_FRAMES, "temperature": 0.0, "samplings": 1}
app.save_config(cfg)
print(f"[cfg] 已切换 LMM -> {MODEL} @ {BASE_URL}")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
app.init_db()

try:
    # 2) 入库视频
    dst = os.path.join(app.VIDEOS_DIR, VID + ".mp4")
    if not os.path.exists(dst):
        shutil.copy(SRC, dst)
    fps, frames, w, h, dur = app.video_meta(dst)
    hsh = app.md5_file(dst)
    conn = app.get_conn(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (VID, os.path.basename(SRC), "upload", None, hsh, round(dur, 2), int(fps),
               f"{w}x{h}", round(os.path.getsize(dst) / 1e6, 2), PROMPT_TEXT, "deepseek-test",
               datetime.datetime.now().isoformat(), None))
    conn.commit(); conn.close()
    print(f"[db] 已入库 {VID} ({w}x{h}, {round(dur,2)}s, {int(fps)}fps)")

    # 3) 抽帧缩放（控成本/控大小）；存全 ASCII 临时目录避开 OpenCV 中文路径坑
    cap = cv2.VideoCapture(dst)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    tdir = tempfile.mkdtemp(prefix="vqframes_")
    paths = []
    for i in range(N_FRAMES):
        idx = min(int(i * total / N_FRAMES), total - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, f = cap.read()
        if not ok:
            continue
        f = cv2.resize(f, (480, 270))
        p = os.path.join(tdir, f"f{i:04d}.jpg")
        if cv2.imwrite(p, f):
            paths.append(p)
    cap.release()
    print(f"[frames] 抽帧 {len(paths)} 张 @ 480x270 -> {tdir}")

    # 4) 冒烟 1 维 (D01)
    d01 = next(d for d in app.DIMENSIONS if d["dim_id"] == "D01")
    smoke = app.score_one_dim(client, MODEL, d01, paths, PROMPT_TEXT, 0.0)
    print(f"[smoke] D01({d01['name']}) -> {smoke}")
    if smoke["value"] is None:
        print("[ABORT] 冒烟失败，DeepSeek vision 未返回有效分数，停止全量。")
        print("  错误:", smoke.get("note"))
    else:
        # 5) 全量 10 维
        results = {}
        for dim in app.DIMENSIONS:
            r = app.score_one_dim(client, MODEL, dim, paths, PROMPT_TEXT, 0.0)
            results[dim["dim_id"]] = r
            print(f"  {dim['dim_id']} {dim['name']:10s} -> value={r['value']} conf={r['confidence']} note={r['note'][:60]}")
        # 6) 落库 objective
        sc = {k: {"value": v["value"], "confidence": v["confidence"], "note": v["note"]}
              for k, v in results.items() if v["value"] is not None}
        conn = app.get_conn(); c = conn.cursor()
        c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (uuid.uuid4().hex[:10], "task_auto", VID, app.DEFAULT_SPEC_ID,
                   "lmm_auto", "lmm_auto", "objective", MODEL,
                   json.dumps(sc, ensure_ascii=False), None, 1, datetime.datetime.now().isoformat()))
        conn.commit(); conn.close()
        print(f"[db] 已落库 objective 分，共 {len(sc)} 维")
        print("\n===== 评分结果汇总 =====")
        for d in app.DIMENSIONS:
            r = results.get(d["dim_id"], {})
            print(f"  {d['dim_id']} {d['name']:10s} {r.get('value')}  | {r.get('note','')[:80]}")
finally:
    app.save_config(backup)
    print("\n[cfg] 已恢复原始 config")
