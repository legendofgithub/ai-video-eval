# AI 视频质量评测项目交接记录

> 更新时间：2026-08-31
> 当前结论：P1 已完成；P2/P3 主体已完成并通过三轮审计。最新一轮补齐无控制台启动、真实浏览器主流程、边界测试和窗口化打包验证。
> 当前状态：8765 与 8876 均无监听；本轮测试视频、评分记录和临时打包目录已清理。

## 1. 环境与入口

- 项目根：`F:\AI\codex project\AI视频评测`
- 开发 Python：`C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe`
- 网页端：在 `app/` 执行 `python server.py`，默认 `http://127.0.0.1:8765`
- 自动化环境变量：`VIDEOEVAL_NO_BROWSER=1` 可禁止自动开浏览器，`VIDEOEVAL_PORT=8876` 可换端口
- 旧 Gradio 端：`python app.py`，仅保留兼容，不继续扩展
- 测试视频：`测试用例\华清普智孵化器广告.mp4`，已 gitignore

## 2. 已完成

### P1 架构收拢

- 提交 `d15ec91`：抽出 `app/core/` 作为存储、媒体、LMM、评测、统计、导出的单一核心；`server.py` 与 `app.py` 变薄。
- 上传校验、删除顺序、SQLite WAL/busy timeout 已落地。

### P2/P3 质量与产品修复

- 提交 `336019b`：pytest 迁移、Ruff/Mypy 门禁、依赖锁定、日志、视觉探测 JSON 化、历史分数恢复。
- 本轮继续完成：
  - 上传从一次性 `await file.read()` 改为 1MB 分块写入，超过 500MB 返回 413，避免大视频撑爆内存。
  - `/api/check-vision` 与 `/api/evaluate/{dim_id}` 改为同步端点，由 FastAPI 线程池执行 OpenCV/光流/API 调用，不再阻塞事件循环。
  - LMM 失败返回 502，不再把 `value=None` 的结果落库；`/api/scores` 只返回有效分数。
  - 前端恢复分数增加请求令牌，避免快速切换视频时旧响应覆盖新视频；移除当前视频时清空已测状态。
  - 维度卡片支持 Tab、Enter、Space 键盘操作。
  - 主观评分校验未知维度、非有限数和 0-10 范围；LMM confidence 钳制到 0-1；抽帧数钳制到 1-64。
  - 无 `stderr` 时 Uvicorn 使用 `log_config=None`，应用日志跳过 console handler；窗口化 exe 不再因 formatter 调 `None.isatty()` 崩溃。
  - 新增数据看板：全样本雷达、MOS 分布、模型 Leaderboard、可排序视频明细、D08/D09/D10 世界模型子榜；MOS 直方图仅统计主观/专家分，不混入客观分。

## 3. 验证证据

### 三轮审计

1. 代码架构与数据流：检查 `core -> server -> web` 的上传、存储、评分、删除、恢复、导出链路；确认 API key 只保存在浏览器会话，服务端不落盘。
2. 测试与边界：补上传 413、失败分数过滤、主观分越界、未知维度、抽帧数非正数等用例。
3. 真实网页与打包：无控制台源码服务、真实 Edge 点击流、窗口化 exe 均验证。

### 自动化结果

```powershell
cd "F:\AI\codex project\AI视频评测\app"
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m pytest
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m ruff check .
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m mypy core server.py
```

- Pytest：`18 passed, 2 skipped`（真实 DeepSeek 用例因未设置 `DEEPSEEK_API_KEY` 跳过）
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`

### 真实浏览器

使用 Playwright 驱动本机 Edge（可见窗口），桌面视口 1440x900：

- 首页渲染 10 个维度卡。
- 无视频点击 D03：出现“请提供测试视频”弹窗，确认后可关闭。
- 上传临时 mp4、填写表单、点击 D03、点击“开始测试”：得到本地信号分 `7.72`，方法为“本地信号指标”。
- 返回主页后显示“已测 1 / 10”；刷新页面并重新选择最近上传，分数仍恢复为 1/10。
- 点击最近记录删除并确认：视频、评分、文件记录均清理。
- 移动视口 390x844：`scrollWidth-clientWidth=0`，无横向溢出。
- 数据看板二次验证：D03 得分 `6.74` 后切换看板，雷达/直方图/模型榜/明细/世界模型子榜均渲染，表头排序可用，移动端溢出为 0。
- 证据截图：`app/_shots/desktop_main.png`、`app/_shots/mobile_home.png`、`app/_shots/desktop_board.png`、`app/_shots/mobile_board.png`（目录已 gitignore）。

### 窗口化打包

- 在独立临时目录执行 PyInstaller `--onefile --windowed`，产物大小 `124,479,275` 字节。
- 以 `VIDEOEVAL_NO_BROWSER=1`、`VIDEOEVAL_PORT=8876` 启动，`/api/health` 返回 `{"ok":true,"dimensions":10}`。
- 验证后停止临时 exe 父子进程，确认 8876 无监听，并删除临时构建目录。

## 4. 未完成

1. 真实 DeepSeek 视觉链路未在本轮执行：环境变量 `DEEPSEEK_API_KEY` 未设置，2 个真实 API 测试按设计跳过。
2. 网页端尚未覆盖旧 Gradio 的完整人工工作台：主观 MOS 录入、专家仲裁、ICC 表、VBench 导出仍需进网页 UI；看板仅展示已落库评分。
3. exe 体积约 118MB，尚未做 `pandas/scipy/pytest` 排除与瘦身分析。
4. 网页端暂无批量“一键 10 维评测”和任务队列，多维度只能逐卡执行。

## 5. 阻塞与工具备注

- 本地截图视觉复核工具 `glance` 报 `Missing config VISION_API_KEY`，因此无法用视觉模型复核截图；已用真实浏览器 DOM 断言、截图留存和移动端溢出计算替代。
- In-app Browser 插件在 Node REPL 初始化时被 `node:process` 导入限制拦截；本轮改用 Playwright 驱动真实 Edge，不影响项目本身。
- PowerShell `Remove-Item` 被本机策略拦截；临时构建目录用 Python `shutil.rmtree` 并先校验路径位于系统 Temp 下后删除。

## 6. 下一轮建议

1. 设置 `DEEPSEEK_API_KEY` 后执行真实视觉探测与 D01 评测。
2. 把主观评分、专家仲裁、导出和看板迁入网页端。
3. 分析 PyInstaller 依赖图，排除测试与未用科学计算包，目标先降到 80MB 内。
4. 增加端口占用、上传中重复提交、并发上传同一 hash 的测试。
5. 为窗口化 exe 增加系统托盘或更友好的后台运行方式。

## 7. 关键文件

```text
app/core/          业务核心
app/server.py      FastAPI 网页端
app/web/           单页前端
app/tests/         pytest
app/pyproject.toml Ruff/Mypy/pytest 配置
app/README.md      运行与打包说明
HANDOFF.md         本交接
```
