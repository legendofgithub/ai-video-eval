# -*- coding: utf-8 -*-
"""验证方案 A：D03/D04 本地信号指标 + 自动评测路由"""
import os, json
import app

VID = "huaqing_ad"
vpath = app.get_video_path(VID)
print("[video]", vpath, "exists=", os.path.exists(vpath) if vpath else False)

# 1) 直接跑本地信号指标（不调 API）
sig = app.signal_metrics(vpath, ["D03", "D04"])
print("[signal_metrics] D03/D04 =", json.dumps(sig, ensure_ascii=False, indent=2))

# 2) 自动评测只选 D03/D04 —— 不应触发任何 LMM/API 调用
res_local = app.auto_evaluate(VID, ["D03", "D04"])
print("[auto_eval D03/D04 only] =", json.dumps(res_local, ensure_ascii=False, indent=2))
assert "D03" in res_local and "D04" in res_local
assert all(res_local[d]["value"] is not None for d in ("D03", "D04")), "本地指标不应为 None"
assert all("本地信号" in (res_local[d]["note"] or "") for d in ("D03", "D04")), "应标记为本地信号"

# 3) 自动评测选全部 10 维 —— 确认 D03/D04 仍来自本地，其余走 LMM 配置
cfg = app.load_config()
print("[config lmm model]", cfg["lmm"]["model"])
res_all = app.auto_evaluate(VID, app.DIM_IDS, prompt_text="孵化器科技创业广告")
print("[auto_eval all 10] 摘要:")
for d in app.DIM_IDS:
    r = res_all.get(d, {})
    tag = "LOCAL" if d in app.TEMPORAL_SIGNAL_DIMS else "LMM"
    print(f"  {d} {app.DIM_NAME[d]:<10} [{tag}] value={r.get('value')} note={r.get('note','')[:40]}")

print("\nSIGNAL TEST OK")
