# AI 视频质量评测工作台（AI Video Evaluation Workbench）

一个**可双击运行、零基础设施**的本地 Web 应用：上传任意一条 AI 生成的视频，用「本地信号指标 + 视觉大模型 + 人工 MOS + 专家仲裁」四种手段，在 10 个维度上打分，产出可诊断、可复现、可与 VBench 对标的评测报告。

> **为什么做它**：2025–2026 年的 AI 视频评测几乎都在「评模型」——喂固定 prompt 集、跑分、上 Leaderboard，需要 GPU 和学术环境（VBench / WorldModelBench / VideoPhy…）。而「评你手头任意一条视频文件」的轻量工具是空白，这个项目就是来补这个空白的。

---

## 核心特性

**三层金字塔 × 10 个评测维度**

| 层 | 维度 | 打分通路 |
|---|---|---|
| 高层 · 世界模型 | D08 物理规律 / D09 人体结构 / D10 常识推理 | 视觉大模型 + 人工 + 专家仲裁 |
| 中层 · 语义对齐 | D05 主体一致性 / D06 背景一致性 / D07 文本-视频对齐 | 视觉大模型 + 人工 |
| 底层 · 技术质量 | D01 成像质量 / D02 美学质量 / D03 时序闪烁 / D04 运动平滑度 | 本地信号（D03/D04）+ 视觉大模型 + 人工 |

**为什么分层**：「画面糊」和「人穿墙」是两种完全不同的失败——前者是渲染管线问题，后者是模型对世界的理解错了。混在一起，报告就只能输出一句「这视频 5.2 分」，毫无诊断价值。

**双路打分**：不是所有维度都该交给大模型。静态抽帧观测不到运动，让模型评「运动平滑度」它自己都会承认无能为力。所以 D03/D04 走纯本地 OpenCV 信号指标（拉普拉斯时序变异系数 + Farneback 光流突变度）——零成本、确定性、可复现；其余 8 维走视觉大模型逐维提问。

**人工评测闭环**：

- 评分工作台内置播放器：0.25×–2× 倍速、按视频真实帧率逐帧步进、一键把当前时间戳打点进备注
- 低分门控：≤4 分必须归因（技术失真 / 语义错位 / 物理常识错误），归因与维度层级不匹配的分数不进入一致性统计
- 专家仲裁按维度覆盖主观均值，保留完整追溯
- 标注员间一致性量化：ICC(2,1) 与 Krippendorff's α，低一致性自动标红

**产出与对比**：数据看板（客观/人工双曲线雷达、MOS 直方图、模型榜、世界模型子榜）+ 一键归档测试记录 + VBench 兼容 JSON 导出。

---

## 快速开始

### 方式一：源码运行（推荐开发者）

```bash
git clone https://github.com/legendofgithub/ai-video-eval.git
cd ai-video-eval/app
pip install -r requirements.txt
python server.py
```

浏览器自动打开 `http://127.0.0.1:8765`。

### 方式二：打包为 exe（双击即用）

```bash
cd app
pip install pyinstaller pystray Pillow
pyinstaller --noconfirm --onefile --windowed --name VideoEvalWeb --add-data "web;web" --hidden-import pystray --collect-all pystray server.py
```

产物 `dist/VideoEvalWeb.exe`（约 120MB）拷到任意 Windows 机器双击即可，接收方**无需安装 Python**。启动后自动打开浏览器；重复双击自动接管已运行实例；端口被占自动顺延。全部数据（数据库、配置、视频、日志）收纳在 exe 旁唯一的 `data/` 文件夹里，删掉它 = 完全重置。

### 配置视觉模型（评测 D01–D02、D05–D10 需要）

在应用首页「测试用模型面板」填写任意 OpenAI 兼容的视觉模型 API：

| 提供方 | Base URL | 模型示例 |
|---|---|---|
| DeepSeek 视觉 | `https://api.deepseek.com/v1` | `deepseek-v4-flash-vision-exp` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` |
| 本地 Ollama（零成本） | `http://localhost:11434/v1` | `deepseek-vl2` |

API Key 只保存在你本机的 `data/config.json`，回显时自动脱敏，**永不上传、不进版本库**。不填 Key 也能用：D03/D04 与人工评分全功能可用。

---

## 使用流程

```
上传视频（填 prompt 与模型标识）
  → 点维度卡逐维测评，或「一键完成测评」跑全部十维
  → 评分工作台：播放器逐帧核对 → 打分 → 低分门控归因
  → 「归档测评结果」存入测评档案页
  → 数据看板：雷达 / 直方图 / 模型榜 / 一致性
  → 导出 VBench 兼容 JSON
```

---

## 项目结构

```
app/
  core/            业务核心（维度定义、存储、媒体、LMM、统计、导出）
  server.py        FastAPI 路由层（薄适配，不含业务逻辑）
  web/             原生单页前端（零框架、零 CDN、图表全手写 SVG）
  tests/           pytest（55+ 用例，存储/媒体/日志全隔离）
  app.py           旧 Gradio 入口（仅保留兼容）
PRD_任务一_平台功能架构设计.md   产品需求：竞品对标、维度模型、技术选型
任务二_数据库Schema.md           SQLite 表结构 = JSON = 导出格式三合一
任务三_评测员SOP.md              标注规范：技术失真 vs 物理常识错误的判别法
app/README.md                    运行、打包、LMM 配置的详细说明
HANDOFF.md                       开发交接记录
```

技术栈：Python 3.11+ / FastAPI / SQLite（WAL）/ OpenCV / 原生 HTML+CSS+JS。前端零 CDN 依赖，断网可正常渲染与本地评测。

---

## 已知边界（诚实清单）

- **不做音频分析**：口型对齐、音画同步、配音质量不在覆盖范围
- **不做 OCR**：画面内文字渲染的正确性没有专项维度
- **不做镜头结构分析**：没有切点检测，多镜头视频只能评连贯性
- **D03/D04 本地指标是启发式**：价值在于确定性与可复现，不宣称与人类感知完全对齐
- **大模型打分不是 ground truth**：它是可复现的近似标注，人工 MOS 与专家仲裁才是校准基准
- **单用户设计**：无账号体系，数据库为本机单文件；多人各自评测请各自部署自己的实例

---

## 文档

- [产品需求与行业调研](PRD_任务一_平台功能架构设计.md)
- [数据库 Schema 设计](任务二_数据库Schema.md)
- [评测员操作规范（SOP）](任务三_评测员SOP.md)
- [运行与打包详解](app/README.md)
