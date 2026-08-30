# -*- coding: utf-8 -*-
"""冒烟测试：验证 DB / 评分落库 / ICC / 导出（不启动 Gradio 服务器）"""
import os, sys, json, sqlite3, datetime, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as A

DB = A.DB
# 清空旧表以复现（沙箱禁止 os.remove，改用 DELETE）
A.init_db()
conn = A.get_conn(); c = conn.cursor()
for t in ("videos", "specs", "scores", "tasks"):
    c.execute(f"DELETE FROM {t}")
conn.commit(); conn.close()

# 插入两个假视频
conn = A.get_conn(); c = conn.cursor()
for vid, tag in [("vid_testA", "self_test_v2"), ("vid_testB", "gen3")]:
    c.execute("INSERT OR REPLACE INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (vid, f"{vid}.mp4", "upload", None, "h", 4.0, 24, "1080x1920", 10.0,
               "a cat jumps", tag, datetime.datetime.now().isoformat(), None))
conn.commit(); conn.close()

# 两个标注员对 vid_testA / vid_testB 的 D08 打分（用于 ICC，需 >=2 视频）
A.save_subjective("vid_testA", "user", "u_001", {"D08": 5, "D01": 8}, "physical", "", "", "")
A.save_subjective("vid_testA", "user", "u_002", {"D08": 6, "D01": 7}, "physical", "", "", "")
A.save_subjective("vid_testB", "user", "u_001", {"D08": 7}, "physical", "", "", "")
A.save_subjective("vid_testB", "user", "u_002", {"D08": 8}, "physical", "", "", "")
# 客观分
obj = {d: {"value": 7.0 if d != "D08" else 5.0, "confidence": 0.8, "note": "ok"} for d in A.DIM_IDS}
conn = A.get_conn(); c = conn.cursor()
c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
          (uuid.uuid4().hex[:10], "t", "vid_testA", A.DEFAULT_SPEC_ID, "lmm_x", "lmm_auto",
           "objective", "deepseek-vl2", json.dumps(obj, ensure_ascii=False), None, 1,
           datetime.datetime.now().isoformat()))
conn.commit(); conn.close()

print("== ICC(D08) ==", A.compute_icc_matrix("D08"))
print("== radar ==", type(A.radar_fig("vid_testA")).__name__)
print("== icc_table ==", A.icc_table()[:2])
out = A.export_vbench()
print("== export ==", out, os.path.exists(out))
print("SMOKE OK")
