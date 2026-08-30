# 任务二：核心数据库 Schema 设计（JSON 示例）

> 配套任务一 PRD v0.3。存储形态 = **本地单文件 SQLite**（`evaluation.db`），以下 JSON 既是「内存结构定义」，也直接对应 SQLite 表行结构与 VBench 兼容导出格式，三者统一。
> 评测维度 = 10 核心维（D01–D10）。评分制 = 10 分制。评测者角色 = `user`（普通标注员）/ `expert`（专家仲裁）/ `lmm_auto`（自动打分）。

---

## 1. 视频基础信息表（Video Info）

### 1.1 字段说明
| 字段 | 类型 | 说明 |
|---|---|---|
| video_id | string | 主键，UUID |
| filename | string | 原始文件名 |
| source | enum | `upload` / `url` |
| url | string? | source=url 时填入 |
| file_hash | string | MD5，用于本机去重 |
| duration_sec | float | 时长 |
| fps | int | 帧率 |
| resolution | string | `WxH` |
| file_size_mb | float | 大小 |
| prompt_text | string? | 生成该视频的文本提示（D07 文本-视频对齐必需） |
| model_tag | string? | 生成模型/版本标识（如 Sora / Gen-3 / 自测v2），用于横向对比 |
| created_at | string | ISO8601 |
| thumbnail_path | string? | 本地缩略图路径 |

### 1.2 JSON 示例
```json
{
  "video_id": "vid_8f3a1c",
  "filename": "cat_jump_01.mp4",
  "source": "upload",
  "url": null,
  "file_hash": "9c2e...a71",
  "duration_sec": 4.0,
  "fps": 24,
  "resolution": "1080x1920",
  "file_size_mb": 11.8,
  "prompt_text": "A ginger cat leaps from a sofa and lands on the floor without breaking a vase",
  "model_tag": "self_test_v2",
  "created_at": "2026-08-30T17:40:12+08:00",
  "thumbnail_path": "data/frames/vid_8f3a1c/thumb.jpg"
}
```

---

## 2. 评测维度配置表（Evaluation Specs）

### 2.1 字段说明
| 字段 | 类型 | 说明 |
|---|---|---|
| spec_id | string | 主键 |
| name | string | 配置名 |
| mos_scale | int | 10（已确认） |
| mode | enum | `objective` / `subjective` / `ab` / `mixed` |
| dimensions | array | 维度定义列表，见下 |

每个 dimension 对象：
| 字段 | 说明 |
|---|---|
| dim_id | `D01`–`D10` |
| name | 维度名 |
| layer | `technical` / `semantic` / `world_model` |
| weight | 默认 1.0 |
| scale | `0-10` |
| anchor_low / anchor_mid / anchor_high | 评分锚定描述（降低主观漂移，见任务三 SOP） |

### 2.2 JSON 示例（默认 10 维配置）
```json
{
  "spec_id": "spec_default_10",
  "name": "Default 10-core (v0.3)",
  "mos_scale": 10,
  "mode": "mixed",
  "dimensions": [
    {"dim_id":"D01","name":"成像质量","layer":"technical","weight":1.0,"scale":"0-10",
     "anchor_low":"明显噪点/模糊/压缩块","anchor_mid":"基本清晰偶有瑕疵","anchor_high":"通透清晰无伪影"},
    {"dim_id":"D02","name":"美学质量","layer":"technical","weight":1.0,"scale":"0-10",
     "anchor_low":"构图混乱/色调脏","anchor_mid":"尚可","anchor_high":"构图与光影专业"},
    {"dim_id":"D03","name":"时序闪烁","layer":"technical","weight":1.0,"scale":"0-10",
     "anchor_low":"持续闪烁/画面跳动","anchor_mid":"偶发微闪","anchor_high":"时序稳定无闪"},
    {"dim_id":"D04","name":"运动平滑度","layer":"technical","weight":1.0,"scale":"0-10",
     "anchor_low":"卡顿/突变/撕裂","anchor_mid":"基本顺滑","anchor_high":"运动自然连贯"},
    {"dim_id":"D05","name":"主体一致性","layer":"semantic","weight":1.0,"scale":"0-10",
     "anchor_low":"主体外观频繁变","anchor_mid":"主体大体一致","anchor_high":"全程主体稳定"},
    {"dim_id":"D06","name":"背景一致性","layer":"semantic","weight":1.0,"scale":"0-10",
     "anchor_low":"背景乱变/穿帮","anchor_mid":"背景基本稳","anchor_high":"背景连贯合理"},
    {"dim_id":"D07","name":"文本-视频对齐","layer":"semantic","weight":1.0,"scale":"0-10",
     "anchor_low":"与prompt严重不符","anchor_mid":"部分符合","anchor_high":"精准还原prompt"},
    {"dim_id":"D08","name":"物理规律","layer":"world_model","weight":1.0,"scale":"0-10",
     "anchor_low":"明显违重力/碰撞/浮力","anchor_mid":"偶有轻微违和","anchor_high":"符合物理规律"},
    {"dim_id":"D09","name":"人体动作与结构","layer":"world_model","weight":1.0,"scale":"0-10",
     "anchor_low":"骨骼/关节明显畸变","anchor_mid":"轻微不自然","anchor_high":"人体结构合理"},
    {"dim_id":"D10","name":"常识推理","layer":"world_model","weight":1.0,"scale":"0-10",
     "anchor_low":"违背常识/因果错乱","anchor_mid":"基本合理","anchor_high":"符合常识与因果"}
  ]
}
```

---

## 3. 评测结果表（Scores）

### 3.1 字段说明
| 字段 | 类型 | 说明 |
|---|---|---|
| score_id | string | 主键 |
| task_id | string | 关联评测任务 |
| video_id | string | 关联视频 |
| spec_id | string | 关联维度配置 |
| rater | object | `{rater_id, role}`；role ∈ `user`/`expert`/`lmm_auto` |
| method | enum | `objective`（LMM/信号）/ `subjective`（人工 MOS）/ `expert_arbitration`（专家仲裁） |
| model | string? | method=objective 时记录所用视觉模型（如 `deepseek-vl2`/`gpt-4o`/`gemini`） |
| scores | object | `{D01:{value,confidence,note}, ... D10}`；objective/subjective 填 value，高层维可记 note（违规类型+时间戳） |
| ab_preference | object? | A-B 模式时 `{vs_video_id, choice, reason}` |
| is_valid | bool | 通过「技术失真 vs 物理常识错误」初判门控则为 true（见任务三） |
| created_at | string | ISO8601 |

> **客观/主观/专家三元区分**：`method` + `rater.role` 共同标识来源。`lmm_auto` 的 method 必为 `objective`；`user` 为 `subjective`；`expert` 可为 `subjective` 或 `expert_arbitration`（仲裁分覆盖普通标注均值）。ICC 计算仅纳入 `method=subjective` 且 `is_valid=true` 的记录。

### 3.2 JSON 示例 A：LMM 客观打分（objective）
```json
{
  "score_id": "sc_aa01",
  "task_id": "task_77",
  "video_id": "vid_8f3a1c",
  "spec_id": "spec_default_10",
  "rater": {"rater_id": "lmm_deepseek_vl2", "role": "lmm_auto"},
  "method": "objective",
  "model": "deepseek-vl2",
  "scores": {
    "D01": {"value": 8.0, "confidence": 0.9, "note": ""},
    "D02": {"value": 7.5, "confidence": 0.8, "note": ""},
    "D03": {"value": 6.0, "confidence": 0.7, "note": "帧 60-72 轻微闪烁"},
    "D04": {"value": 7.0, "confidence": 0.8, "note": ""},
    "D05": {"value": 8.5, "confidence": 0.9, "note": ""},
    "D06": {"value": 8.0, "confidence": 0.85, "note": ""},
    "D07": {"value": 9.0, "confidence": 0.95, "note": "精准还原prompt"},
    "D08": {"value": 7.0, "confidence": 0.8, "note": "落地点轻微穿地"},
    "D09": {"value": null, "confidence": null, "note": "视频无人物"},
    "D10": {"value": 8.0, "confidence": 0.85, "note": ""}
  },
  "ab_preference": null,
  "is_valid": true,
  "created_at": "2026-08-30T17:45:00+08:00"
}
```

### 3.3 JSON 示例 B：人工主观打分（subjective，普通标注员）
```json
{
  "score_id": "sc_u019",
  "task_id": "task_77",
  "video_id": "vid_8f3a1c",
  "spec_id": "spec_default_10",
  "rater": {"rater_id": "u_001", "role": "user"},
  "method": "subjective",
  "model": null,
  "scores": {
    "D01": {"value": 8, "confidence": null, "note": ""},
    "D08": {"value": 6, "confidence": null, "note": "猫落地后花瓶轻微穿模"},
    "D10": {"value": 7, "confidence": null, "note": ""}
  },
  "ab_preference": null,
  "is_valid": true,
  "created_at": "2026-08-30T17:50:30+08:00"
}
```

### 3.4 JSON 示例 C：专家仲裁（expert_arbitration，覆盖争议）
```json
{
  "score_id": "sc_e003",
  "task_id": "task_77",
  "video_id": "vid_8f3a1c",
  "spec_id": "spec_default_10",
  "rater": {"rater_id": "exp_tony", "role": "expert"},
  "method": "expert_arbitration",
  "model": null,
  "scores": {
    "D08": {"value": 5, "confidence": null, "note": "仲裁：穿模属物理违规，下调"}
  },
  "ab_preference": null,
  "is_valid": true,
  "created_at": "2026-08-30T18:05:00+08:00"
}
```

---

## 4. VBench 兼容导出（对标用）

将多视频、多模型的主观/客观均分汇总为 Leaderboard 格式，便于与公开 Benchmark 横向对标：
```json
{
  "export_version": "vbench_compat_1.0",
  "spec_id": "spec_default_10",
  "mos_scale": 10,
  "leaderboard": [
    {
      "model_tag": "self_test_v2",
      "mean_scores": {"D01":8.1,"D02":7.4,"D03":6.2,"D04":7.1,"D05":8.4,
                      "D06":8.0,"D07":8.8,"D08":6.5,"D09":null,"D10":7.9},
      "layer_means": {"technical":7.2,"semantic":8.4,"world_model":7.5},
      "n_annotators": 3, "icc": 0.82, "krippendorff_alpha": 0.79
    }
  ]
}
```

> **ICC/Krippendorff's α** 仅基于 `method=subjective & is_valid=true` 的多次评分计算，低于阈值（建议 ICC<0.6）的维度在面板高亮预警（见任务一模块 D）。
