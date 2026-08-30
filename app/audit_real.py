# -*- coding: utf-8 -*-
"""项目诚实审计：真实执行核心链路，逐项给出证据，不依赖外部 API（LMM 路径此前已独立验证）。"""
import os, json, shutil
import numpy as np
import app

SRC = r"F:\AI\codex project\AI视频评测\测试用例\华清普智孵化器广告.mp4"
PASS = []; FAIL = []; FLAG = []
def ok(name, cond, ev=""):
    (PASS if cond else FAIL).append(f"{name} | {ev}")
    print(f"[{'PASS' if cond else 'FAIL'}] {name} | {ev}")

print("=== AUDIT 开始（本地链路，无外部 API） ===\n")

# [0] 模块导入 + UI 构建（import 即执行 init_db + gr.Blocks 构建）
ok("0. 模块导入与 UI 构建", True, "导入未抛异常即说明 gr.Blocks 结构可构建")

# [1] add_video 真实入库（用测试视频源文件，随后清理）
class FO: name = SRC
vid2, msg2 = app.add_video(FO(), None, "孵化器科技创业广告", "audit_model")
ok("1. add_video 入库", bool(vid2), f"video_id={vid2}, {msg2}")

# [2] 本地信号指标（D03/D04）真实计算
vpath = app.get_video_path(vid2)
sig = app.signal_metrics(vpath, ["D03", "D04"])
ok("2. 本地信号 D03/D04", sig["D03"]["value"] is not None and sig["D04"]["value"] is not None,
   f"D03={sig['D03']['value']}, D04={sig['D04']['value']}")

# [3] save_subjective 落库 + is_valid 门控逻辑
# 高层 D08=3 且 gate=physical -> 应 is_valid=1；若 gate=na -> 应 is_valid=0（暴露误判）
r_phys = app.save_subjective(vid2, "user", "aud_r1", {"D08": 3}, "physical", "", "", "")
r_na = app.save_subjective(vid2, "user", "aud_r2", {"D08": 3}, "na", "", "", "")
conn = app.get_conn(); c = conn.cursor()
c.execute("SELECT rater_id, is_valid FROM scores WHERE video_id=? AND rater_id IN ('aud_r1','aud_r2') ORDER BY rater_id", (vid2,))
rows = c.fetchall(); conn.close()
valid_map = {r[0]: r[1] for r in rows}
ok("3a. save_subjective 落库", "已保存" in r_phys and "已保存" in r_na, f"{r_phys}; {r_na}")
ok("3b. is_valid 门控(物理低分+gate=physical 有效)", valid_map.get("aud_r1") == 1, f"aud_r1 is_valid={valid_map.get('aud_r1')}")
ok("3c. is_valid 门控(物理低分+gate=na 无效)", valid_map.get("aud_r2") == 0, f"aud_r2 is_valid={valid_map.get('aud_r2')}")

# [4] compute_icc_matrix（跨视频真实 ICC）— 当前 DB 可能样本不足，调用并如实报告
icc = app.compute_icc_matrix("D08")
ok("4. compute_icc_matrix 不崩", True, f"返回={icc}（None=样本不足；此前 smoke 测试已算出=1.0）")

# [5] compute_icc（单视频）真相：返回的是 std 而非 ICC —— 桩函数
icc_single = app.compute_icc(vid2, "D08")
FLAG.append(f"5. compute_icc(单视频) 实为 np.std(vals)={icc_single}，并非 ICC(2,1)；是占位桩，UI 未调用，但命名误导，应改名或删除")
print(f"[FLAG] 5. compute_icc(单视频) 返回值={icc_single} —— 实为标准差占位，不是 ICC")

# [6] radar_fig 真实生成
fig = app.radar_fig(vid2)
ok("6. radar_fig 生成", hasattr(fig, "data") and len(fig.data) >= 1, f"traces={len(fig.data)}")

# [7] comparison_fig 真实生成
figc = app.comparison_fig()
ok("7. comparison_fig 生成", hasattr(figc, "data"), f"traces={len(figc.data)}")

# [8] export_vbench 真实写出
out = app.export_vbench()
ok("8. export_vbench 写出", os.path.exists(out), out)
exp = json.load(open(out, encoding="utf-8"))
print(f"     leaderboard 条目数={len(exp.get('leaderboard', []))}")

# [9] 方法学缺陷：radar_fig 混合 objective/subjective/仲裁 均值
conn = app.get_conn(); c = conn.cursor()
c.execute("SELECT method, COUNT(*) FROM scores WHERE video_id=? GROUP BY method", (vid2,))
mm = c.fetchall(); conn.close()
FLAG.append(f"9. radar_fig 对该视频各 method 行数={mm}；雷达图对所有 method 分数取均值，未区分客观/主观/专家仲裁，会把 LMM 分与人工 MOS 混算进同一雷达")
print(f"[FLAG] 9. 雷达图数据源 method 分布={mm}（客观与主观被混算）")

# [10] 专家仲裁是否真"覆盖"？检查 expert_arbitration 是否仅新增一行而非解析冲突
r_exp = app.save_subjective(vid2, "expert", "exp_tony", {"D08": 9}, "na", "", "", "")
conn = app.get_conn(); c = conn.cursor()
c.execute("SELECT method, COUNT(*) FROM scores WHERE video_id=? GROUP BY method", (vid2,))
mm2 = c.fetchall(); conn.close()
FLAG.append(f"10. 专家仲裁(save_subjective role=expert)仅新增一行 method=expert_arbitration，未程序化'覆盖/解决'既有分歧；雷达图仍会把专家分与人工分平均。所谓'仲裁覆盖'名不副实")
print(f"[FLAG] 10. 专家仲裁后 method 分布={mm2}（仅新增行，无冲突解析）")

print("\n=== 清理审计污染（仅删 aud_/exp_tony 在 vid2 的行 + vid2 视频记录）===")
conn = app.get_conn(); c = conn.cursor()
c.execute("DELETE FROM scores WHERE video_id=? AND rater_id IN ('aud_r1','aud_r2','exp_tony')", (vid2,))
c.execute("DELETE FROM videos WHERE video_id=?", (vid2,))
conn.commit(); conn.close()
# 视频文件移入审计垃圾箱（沙箱禁 os.remove，用 move）
trash = os.path.join(app.VIDEOS_DIR, "_audit_trash"); os.makedirs(trash, exist_ok=True)
fp = app.get_video_path(vid2)
if fp and os.path.exists(fp):
    shutil.move(fp, os.path.join(trash, os.path.basename(fp)))
print(f"已清理 vid2={vid2} 的审计数据")

print(f"\n=== 结果：PASS={len(PASS)}  FAIL={len(FAIL)}  FLAG={len(FLAG)} ===")
for x in FAIL: print("  FAIL:", x)
for x in FLAG: print("  FLAG:", x)
print("AUDIT DONE")
