# -*- coding: utf-8 -*-
"""验证审计修复：compute_icc 桩删除 / 雷达图双 trace / 专家仲裁覆盖主观分"""
import os, json, shutil
import numpy as np
import app

SRC = r"F:\AI\codex project\AI视频评测\测试用例\华清普智孵化器广告.mp4"
PASS=[]; FAIL=[]
def ok(n,c,ev=""):
    (PASS if c else FAIL).append(f"{n}|{ev}"); print(f"[{'PASS' if c else 'FAIL'}] {n}|{ev}")

# A) compute_icc 桩已删除
ok("A. compute_icc 占位桩已删除", not hasattr(app, "compute_icc"),
   "hasattr=%s" % hasattr(app, "compute_icc"))

# 造一个临时视频用于隔离测试
class FO: name = SRC
vid, msg = app.add_video(FO(), None, "fix_verify", "model_X")
print("临时视频:", vid)

# B) 插入客观分行（合成 all-10 维）测雷达机器 trace
conn=app.get_conn(); c=conn.cursor()
obj_scores={d:{"value":7.0,"confidence":0.9,"note":"synthetic"} for d in app.DIM_IDS}
c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
          ("fix_obj","task_auto",vid,app.DEFAULT_SPEC_ID,"lmm_deepseek","lmm_auto","objective",
           "deepseek-v4-flash-vision-exp",json.dumps(obj_scores,ensure_ascii=False),None,1,
           "2026-01-01T00:00:00"))
conn.commit(); conn.close()

# C) 两个主观标注员（valid），值与客观不同，测人工 trace
app.save_subjective(vid,"user","f_r1",{"D01":3,"D08":4},"na","","","")  # 高层D08=4,gate=na -> invalid!
# 注意：D08<=4 且 gate!=physical -> is_valid=0，故该主观行不计入有效人工分。改用 gate=physical 使其有效
app.save_subjective(vid,"user","f_r1",{"D01":3,"D08":4},"physical","","","")
app.save_subjective(vid,"user","f_r2",{"D01":5,"D08":6},"physical","","","")
# 人工有效均值应为 D01=(3+5)/2=4, D08=(4+6)/2=5

# D) 专家仲裁（覆盖）
app.save_subjective(vid,"expert","exp_tony",{"D01":9,"D08":2},"na","","","")  # 专家 D01=9,D08=2

# E) 雷达图：机器 trace 应为 7.0；人工 trace 应为专家值(9,2) 而非主观均值(4,5)
fig = app.radar_fig(vid)
names=[t.name for t in fig.data]
ok("E1. 雷达含'机器客观分' trace", "机器客观分(LMM+本地信号)" in names, str(names))
ok("E2. 雷达含'人工/专家分' trace", "人工/专家分(MOS)" in names, str(names))
# 找到人工 trace 的 r 值（前10个为 D01..D10）
human_trace = next(t for t in fig.data if t.name=="人工/专家分(MOS)")
obj_trace = next(t for t in fig.data if t.name=="机器客观分(LMM+本地信号)")
ok("E3. 机器 trace 全维=7.0", list(obj_trace.r[:10])==[7.0]*10, str(list(obj_trace.r[:10])))
# 人工 trace 应为专家值：D01=9, D08=2（索引0和7）
hv=list(human_trace.r[:10])
ok("E4. 人工 trace=专家覆盖值(D01=9,D08=2)", abs(hv[0]-9)<1e-6 and abs(hv[7]-2)<1e-6, f"D01={hv[0]},D08={hv[7]}")
ok("E5. 专家值≠主观均值(4,5) 证明确实覆盖", not(abs(hv[0]-4)<1e-6 and abs(hv[7]-5)<1e-6), f"D01={hv[0]},D08={hv[7]}")

# F) comparison_fig / export 使用人工有效分（含专家覆盖）
fc=app.comparison_fig(); ok("F1. comparison_fig 有 bars", len(fc.data)>0, f"traces={len(fc.data)}")
out=app.export_vbench(); ok("F2. export_vbench 写出", os.path.exists(out), out)
exp=json.load(open(out,encoding="utf-8"))
mt=[e["model_tag"] for e in exp["leaderboard"]]
ok("F3. 导出含 model_X", "model_X" in mt, str(mt))
# model_X 的 D01 应为专家值 9（覆盖），D08=2
mxe=next(e for e in exp["leaderboard"] if e["model_tag"]=="model_X")
ok("F4. 导出 D01=专家值9(覆盖)", abs(mxe["mean_scores"]["D01"]-9)<1e-6, f"D01={mxe['mean_scores']['D01']}")
ok("F5. 导出 D08=专家值2(覆盖)", abs(mxe["mean_scores"]["D08"]-2)<1e-6, f"D08={mxe['mean_scores']['D08']}")

# 清理临时视频
conn=app.get_conn(); c=conn.cursor()
c.execute("DELETE FROM scores WHERE video_id=?", (vid,))
c.execute("DELETE FROM videos WHERE video_id=?", (vid,))
conn.commit(); conn.close()
fp=app.get_video_path(vid)
if fp and os.path.exists(fp):
    trash=os.path.join(app.VIDEOS_DIR,"_audit_trash"); os.makedirs(trash,exist_ok=True)
    shutil.move(fp, os.path.join(trash, os.path.basename(fp)))
print("已清理临时视频", vid)
print(f"\n结果 PASS={len(PASS)} FAIL={len(FAIL)}")
for x in FAIL: print("  FAIL:", x)
print("VERIFY DONE")
