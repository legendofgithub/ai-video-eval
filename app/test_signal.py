# -*- coding: utf-8 -*-
"""自包含信号指标测试：自建测试视频、验证 D03/D04 本地出分与降级路由。"""
import json

import core

SRC = r"F:\AI\codex project\AI视频评测\测试用例\华清普智孵化器广告.mp4"

r = core.add_video(SRC, "信号指标自检", "signal_test")
VID = r["video_id"]
assert not r["duplicate"], "测试视频不应复用旧记录"
print("[setup] video_id =", VID)

try:
    vpath = core.get_video_path(VID)
    print("[video]", vpath)

    # 1) 本地信号指标（不调任何 API）
    sig = core.signal_metrics(vpath, ["D03", "D04"])
    print("[signal_metrics]", json.dumps(sig, ensure_ascii=False, indent=2))
    assert all(sig[d]["value"] is not None for d in ("D03", "D04")), "本地指标不应为 None"
    assert all("本地信号" in (sig[d]["note"] or "") for d in ("D03", "D04")), "应标记为本地信号"

    # 2) 自动评测只选 D03/D04 —— 不应触发任何 LMM/API 调用
    res_local = core.auto_evaluate(VID, ["D03", "D04"])
    assert all(res_local[d]["value"] is not None for d in ("D03", "D04")), "本地维度路由失败"

    # 3) 全 10 维：D03/D04 本地出分，其余无 Key 时优雅降级（不崩溃）
    res_all = core.auto_evaluate(VID, core.DIM_IDS, prompt_text="孵化器科技创业广告")
    for d in core.DIM_IDS:
        tag = "LOCAL" if d in core.TEMPORAL_SIGNAL_DIMS else "LMM"
        v = res_all.get(d, {})
        print(f"  {d} {core.DIM_NAME[d]:<10} [{tag}] value={v.get('value')} note={(v.get('note') or '')[:48]}")
    assert all(res_all[d]["value"] is not None for d in ("D03", "D04"))
    assert all(res_all[d]["value"] is None for d in core.DIM_IDS
               if d not in core.TEMPORAL_SIGNAL_DIMS), "无 Key 时 LMM 维应降级为 None"

    print("\nSIGNAL TEST OK")
finally:
    core.delete_video(VID)
    print("[teardown] removed", VID)
