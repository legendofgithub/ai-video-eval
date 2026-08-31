# -*- coding: utf-8 -*-
"""10-core evaluation dimensions (aligned with PRD v0.3 and Task-2 schema)."""

DIMENSIONS: list[dict] = [
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

# D03/D04 use local CPU signal metrics: static frames cannot observe
# flicker or motion, so these two dimensions bypass the LMM by default.
TEMPORAL_SIGNAL_DIMS = {"D03", "D04"}
