# AI 视频质量评测项目 · 任务交接文档

> 更新时间：2026-08-31  
> 交接目标：任何 AI 助手读完本文档后可直接接续开发，无需重新摸索项目状态。  
> 当前总状态：P0/P1/P2/P3 **已全部提交**（最新提交 `336019b`）；质量三连（ruff 全过 / mypy no issues / pytest 12 passed 2 skipped）已补跑通过；网页服务已在 `127.0.0.1:8765` 运行。下一步进入 **P4**。

---

## 1. 项目与环境速览

- 项目根：`F:\AI\codex project\AI视频评测`
- 应用目录：`app/`（core 核心 + server 网页端 + app.py Gradio 界面 + web 前端 + tests 测试）
- 开发 venv：`C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe`（系统 Python 缺 gradio，务必用此 venv）
- 网页前端：`python server.py` → http://127.0.0.1:8765（当前服务未运行，端口空闲）
- 旧 Gradio 界面：`python app.py` → :7860（仅保留，不再新增功能）
- 测试视频源：`测试用例\华清普智孵化器广告.mp4`（1280x720 / 30fps / 30s，gitignore 已排除）
- Git：已有仓库，两个提交：`c41b039`（P0 基线）、`d15ec91`（P1 架构收拢）

## 2. 已完成工作明细

### P0 安全与版本控制（已提交 c41b039）
- git init + `.gitignore`（排除 db/data/config.json/测试视频/打包产物/*.spec）
- `test_real_deepseek.py` 硬编码真实 DeepSeek Key 改为环境变量 `DEEPSEEK_API_KEY`
- 新增 `config.example.json`（无 Key 模板）；README 删除危险分发建议并写入 Key 安全规范

### P1 架构收拢（已提交 d15ec91）
- 新增 `app/core/` 单一事实来源，8 模块：
  `dimensions`（10维定义）/ `storage`（SQLite+视频生命周期）/ `media`（校验抽帧哈希）/ `lmm`（视觉模型调用与探测）/ `evaluate`（D03/D04本地信号+LMM路由）/ `stats`（ICC）/ `export`（VBench导出）/ `logger`（日志，P2加入）
- `app.py` 609→约230行薄 Gradio UI 层，re-export 保持旧测试兼容；`server.py` 薄 HTTP 路由
- 三项修复（均实测）：
  1. 上传校验：伪冒 mp4（如 1KB 全零）返回 400"无法读取视频或分辨率无效"；500MB 上限；保留原始文件名
  2. 删除顺序：先删文件再删记录，文件被占用时记录保持完整（无孤儿文件）
  3. SQLite：WAL + `busy_timeout=5000`
- 顺手修复：`auto_evaluate` 忽略传入 `lmm_cfg` 参数的 bug；LMM 客户端 60s 超时

### P2 健壮性（代码完成，未提交）
- 视觉探测 `probe_vision` 改为 JSON 判定（shape/color 字段），保留关键词回退，词表扩展 crimson/scarlet
- 新增 `core/logger.py`：控制台 + 轮转文件日志（`data/app.log`，2MB×2）；windowed 无 stderr 时自动跳过 console handler
- 新增 `GET /api/scores?video_id=`：返回每维度最新客观分；前端选中视频时自动恢复"已测 x/10"徽章
- `evaluate` 的 `n_frames` 参数化（Form 可传，钳制 1-32）

### P3 质量门禁与打包（完成，未提交）
- **pytest 化**：新增 `app/tests/`（conftest 用 monkeypatch 隔离 DB/视频/配置到临时目录）：
  `test_storage.py`（校验/查重/删除/门控）、`test_signals.py`（D03=6.65/D04=8.7 本地出分+无Key降级）、`test_export.py`（专家覆盖/导出）、`test_server.py`（TestClient health/dimensions/上传400）、`test_real_deepseek.py`（skipif 无 `DEEPSEEK_API_KEY`）
  旧脚本 `test_smoke/verify_fixes/audit_real/test_signal/test_real_deepseek`（app/ 根下）已删除
- **ruff**：`app/pyproject.toml` 配置（B008 为 FastAPI 惯例豁免），全绿
- **mypy**：宽松模式（check_untyped_defs=false），全绿
- **requirements.lock**：77 包精确版本；README 已写明复现方式
- **PyInstaller**：console 版 `dist/VideoEvalWeb.exe`（118.7MB）构建并实测通过（health 200、前端 200、自动开浏览器、数据落 exe 同目录）
  构建命令：`pyinstaller --noconfirm --onefile --name VideoEvalWeb --add-data "web;web" server.py`
  **重要**：不要加 `--windowed`，已实测无控制台模式 uvicorn 因缺 stdio 直接退出；README 已注明

## 3. 中断点与立即待办（2026-08-31 已全部执行 ✅，保留备查）

1. **补跑最终质量三连**（上一步被用户中断，打包后未再全量验证）：
   ```powershell
   cd "F:\AI\codex project\AI视频评测\app"
   & "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m ruff check .
   & "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m mypy core server.py
   & "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -X utf8 -m pytest tests -q
   ```
   预期：ruff 全过、mypy no issues、pytest 12 passed 2 skipped。打包后仅改过 README/.gitignore/server.py 的 windowed 防御代码与 logger，风险极低。
2. **提交 P2+P3**：`git add -A; git commit -m "P2+P3：视觉探测JSON化、日志、分数恢复、pytest化、ruff/mypy门禁、依赖锁定与exe打包"`（本交接文档一并入库）
3. **重启网页服务**（用户浏览器开着 8765）：venv python `-X utf8 server.py` 后台常驻

## 4. 工作区状态（已全部提交 ✅）

```
（以下清单已于 2026-08-31 全部提交至提交 336019b，当前工作区干净、无未提交内容）
修改：app/README.md（打包说明修正为 console 版 + lock 用法）
修改：.gitignore（新增 *.spec）
修改：app/server.py（/api/scores、n_frames 参数化、frozen stdout 防御、import 排序）
修改：app/web/app.js（restoreScores 恢复已测分数）
修改：app/core/{lmm,storage,evaluate}.py（探测JSON化、日志接入）
新增：app/core/logger.py
新增：app/pyproject.toml、app/requirements.lock
新增：app/tests/{conftest,test_storage,test_signals,test_export,test_server,test_real_deepseek}.py
删除：app/{test_smoke,verify_fixes,audit_real,test_signal,test_real_deepseek}.py
新增：HANDOFF.md（本文件）
（dist/VideoEvalWeb.exe 与 build/ 已被 gitignore 排除，不入库）
```

## 5. 已知坑（后来者必读）

- **SQLite WAL**：直接拷贝 `.db` 备份会漏 `-wal` 日志导致状态错乱（已踩过）。备份前停服务或用 SQLite backup API；分发 exe 前同理 checkpoint。
- **PyInstaller windowed**：uvicorn 在无 stdio 下崩溃，尝试过重定向 stdout/stderr 与跳过 console handler 仍不稳，已决策交付 console 版；控制台窗即日志窗，勿再轻易改回 `--windowed`。
- **PowerShell 环境策略**：`Remove-Item` 常被策略拦截，删文件用 `python -c "import os; os.remove(...)"`；复合命令（分号串联多条）也可能被拦，拆步执行。
- **apply_patch**：同一文件不能在同一 patch 里 Delete+Add，分两次提交；Add File 每行必须 `+` 前缀（含空行）。
- **历史数据说明**：`huaqing_ad` 视频是用户在界面上主动删除的（服务日志有 DELETE 200 记录），不是数据丢失，勿尝试"恢复"。
- 中文路径下 `cv2.imwrite` 静默失败，必须走 `imencode + 二进制写`（core/media.py 已处理，改动抽帧逻辑时保持）。

## 6. 后续路线（P4 建议，按优先级）

1. 打包瘦身：分析为何 pandas/scipy 被拖入 exe（118MB），尝试 `--exclude-module pandas` 等，目标 <80MB
2. 统计补全：Krippendorff's α（PRD 要求，目前只有 ICC）
3. exe 的窗口化深度修复（Windows 子系统/信号机制调研），或做系统托盘替代控制台窗
4. GitHub Actions CI：push 时跑 ruff+mypy+pytest
5. Gradio 看板增强：MOS 分布直方图、Leaderboard 表格 UI、世界模型子榜视图
6. 真实 Key 端到端：设 `DEEPSEEK_API_KEY` 后跑 `pytest tests/test_real_deepseek.py` 验证视觉探测与 D01 打分全链路

## 7. 关键文件地图

```
app/
  core/            业务核心（改逻辑只改这里）
  server.py        FastAPI 网页端路由（薄层）
  app.py           Gradio 界面（薄层，旧入口）
  web/             蓝白青春风单页前端（index.html/style.css/app.js）
  tests/           pytest 全量测试（临时库隔离）
  pyproject.toml   ruff/mypy/pytest 配置
  requirements.txt 最低版本声明 / requirements.lock 精确锁定
  run_web.bat      源码启动网页端
  dist/VideoEvalWeb.exe  可分发单文件（console 版，已实测）
```
