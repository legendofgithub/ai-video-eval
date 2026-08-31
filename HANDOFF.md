# AI 视频质量评测项目交接记录

> 更新时间：2026-08-31 16:32 +08:00
> 当前结论：P1/P2/P3 已完成；P4 的主观评分、专家仲裁、可靠性、VBench 导出、托盘与边界测试、产品介绍页也已进入网页端。本轮增量审计修复统计口径、测试隔离、端口占用和真实 UI 状态问题，并已全部提交。
> 当前 Git：`master` HEAD=`3ff9be7`；工作区干净（`nothing to commit, working tree clean`），无未提交改动、无回滚。
> 当前运行状态：本轮启动的 `8765` 已停止；`8876` 有本轮开始前已存在的 Python 进程 `34124` 监听，按“只停止自己启动的服务”未处理。数据库回到 `videos=0, scores=0`，本轮视频、评分、导出与临时脚本已清理。

## 1. 环境与入口

- 项目根：`F:\AI\codex project\AI视频评测`
- 开发 Python：`C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe`
- 网页端：在 `app/` 执行 `python server.py`，默认 `http://127.0.0.1:8765`
- 自动化环境变量：`VIDEOEVAL_NO_BROWSER=1` 禁止自动开浏览器，`VIDEOEVAL_PORT` 指定端口
- 旧 Gradio 端：`python app.py`，仅保留兼容，不继续扩展
- 本地测试视频：`测试用例\华清普智孵化器广告.mp4`，已 gitignore

## 2. 已完成

### P1 架构收拢

- 提交 `d15ec91`：抽出 `app/core/` 作为存储、媒体、LMM、评测、统计、导出的单一核心；`server.py` 与 `app.py` 变薄。
- 上传校验、删除顺序、SQLite WAL/busy timeout 已落地。

### P2/P3 工程与产品质量

- 提交 `336019b`：pytest 迁移、Ruff/Mypy 门禁、依赖锁定、日志、视觉探测 JSON 化、历史分数恢复。
- 上传改为 1MB 分块写入，超过 500MB 返回 413；OpenCV/光流/API 调用走线程池；LMM 失败不落库。
- 前端分数恢复带请求令牌，维度卡片支持键盘操作；主观分、confidence、抽帧数均有边界钳制。
- 无控制台/windowed 模式日志兼容；数据看板包含雷达、MOS 直方图、模型榜、可排序明细和世界模型子榜。

### P4 网页工作台

- 提交 `0f72bc8`：新增 `/api/dashboard` 聚合与原生 SVG 看板。
- 提交 `2bbb6e3`：主观评分、专家仲裁、ICC/Krippendorff、VBench 导出、评分工作台、系统托盘和重复上传/端口测试。
- 提交 `8a57d16`：新增顶部"产品介绍"视图，展示工程架构与 Benchmark 出题/人工评测素质，桌面/移动端验证无横向溢出。

### 本轮增量审计修复（已提交 `3ff9be7`）

- commit `3ff9be7`（12 files, +266/-91，含新增 `app/tests/test_stats.py`）。
- 提交前质量三连复核：pytest `31 passed, 2 skipped`；ruff `All checks passed!`；mypy `Success: no issues found in 10 source files`。

1. **统计口径**
   - `compute_icc_matrix` 从一致性单评分公式修正为 ICC(2,1) 绝对一致性公式，补上列效应项。
   - `compute_krippendorff_alpha` 改为 interval 数据的 coincidence-matrix 公式；用独立参考实现核对基准，例如两单元 `[1,2]` / `[3,4]` 的正确值为 `0.70`，原实现误算 `0.75`。
   - 导出按时间顺序读取，最新专家仲裁覆盖旧仲裁。
2. **测试隔离与边界**
   - `conftest.py` 增加 autouse 存储/媒体隔离，所有 pytest 均不再把视频、抽帧或数据库记录写入真实 `app/data`。
   - 本地 D03/D04 失败分直接返回 502，不再插入 `value=None`。
   - 主观评分拒绝空维度、空白评测者 ID 和未知低分门控。
3. **运行与 UI**
   - `is_port_free` 真正接入启动流程；端口占用时记录日志、windowed 下弹窗提示并以退出码 2 结束。
   - 上传成功响应带 `prompt_text/model_tag`，重复上传在待测试区仍显示模型标识。
   - 全局 `[hidden] { display:none !important; }` 修复 `.pending-video` 的 `display:flex` 覆盖 `hidden` 导致的空占位问题。
   - 可靠性表文案改为“仅统计有效人工标注评分”，与实际查询口径一致。

## 3. 验证证据

### 三轮审计

1. **代码架构与数据流**：复核 `core -> server -> web` 的上传、存储、评分、可靠性、导出、删除链路；确认本轮改动未破坏 API key 不落盘约束。
2. **测试与边界**：新增统计回归、失败本地分、空主观分、空白评测者、未知门控、最新专家仲裁、重复上传响应与媒体隔离断言。
3. **真实网页点击**：可见 Edge + Playwright 覆盖真实表单、按钮、上传、评测、工作台、导出、看板、排序、删除与移动端。

### 质量门禁

```powershell
cd "F:\AI\codex project\AI视频评测\app"
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m pytest
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m ruff check .
& "C:\Users\asus\.workbuddy\binaries\python\envs\videoeval\Scripts\python.exe" -m mypy core server.py
```

- Pytest：`31 passed, 2 skipped`（2 个真实 DeepSeek 用例因未设置 `DEEPSEEK_API_KEY` 跳过）
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`
- `git diff --check`：通过

### 真实 Edge 点击流

- 桌面 `1440x900`：首页 10 张维度卡、无待测视频时待测占位隐藏、无横向溢出。
- 展开高级选项，填写 prompt 与 `audit_edge`，上传临时 mp4；新上传和重复上传都显示模型标识。
- 点击 D03 -> “开始测试”，得到本地信号分 `7.86`。
- 评分工作台：选择人工标注员 `audit_r1`，设置 D01=7.5、D08=8，保存成功；10 行可靠性表渲染。
- 下载 VBench JSON，`leaderboard` 包含 `audit_edge`。
- 数据看板：雷达、直方图、模型榜、明细和世界模型子榜渲染；D03 表头排序可用；无横向溢出。
- 删除最近上传并确认：`/api/videos` 为空，数据库 `videos=0, scores=0`，本轮视频/抽帧/导出/脚本清理。
- 移动端 `390x844`：无横向溢出。
- 截图证据：`app/_shots/audit_desktop_home.png`、`audit_desktop_d03.png`、`audit_desktop_workbench.png`、`audit_desktop_board.png`、`audit_mobile_home.png`（目录 gitignored）。
- 端口占用：在 `8765` 已监听时再次启动，日志输出占用提示并退出，退出码 `2`。

### 打包历史证据

- PyInstaller `--onefile --windowed` 曾生成 `124,479,275` 字节 exe。
- `8876` 健康 200、托盘/无浏览器环境变量已验证；当时临时 exe 与构建目录已清理。
- 瘦身按用户要求跳过，体积非当前约束。

## 4. 未完成

1. 真实 DeepSeek 视觉链路仍未执行：缺少用户持有的 `DEEPSEEK_API_KEY`，2 个真实 API 测试按设计跳过。
2. 网页端还没有“一键 10 维评测”和任务队列，多维度仍需逐卡执行。
3. ~~本轮改动未提交~~ 已解决：本轮改动已提交为 `3ff9be7`，可直接开始新功能。
4. 可靠性统计当前只统计人工标注员，专家仲裁作为导出覆盖值，不参与 ICC/Krippendorff；若产品希望专家也参与一致性，需要先定义口径。
5. `app/data` 中存在历史孤儿媒体/日志文件；本轮只删除本轮生成和本轮测试对应数据，未清理可能属于用户的历史运行数据。

## 5. 阻塞与外部状态

- `DEEPSEEK_API_KEY` 是真实视觉链路唯一产品级阻塞。
- `8876` 被进程 `34124`（`videoeval` Python 环境 `server.py`）占用。该进程在本轮开始前已存在，不是本轮启动，未按指令擅停。
- 本地视觉复核 `glance` 缺 `VISION_API_KEY`；本轮以真实浏览器 DOM 断言、截图和溢出计算替代。
- PowerShell `Remove-Item` 会被本机策略拦截；本轮仅用 Python 删除两个已校验路径的临时文件，未做递归删除。

## 6. 下一轮建议

1. （已完成）本轮统计、隔离、端口和 UI 修复已提交为 `3ff9be7`。
2. 设置 `DEEPSEEK_API_KEY` 后执行 2 个真实视觉用例，并在网页端跑一次非 D03 维度。
3. 设计“一键 10 维评测”任务队列：并发、取消、失败重试、逐维结果恢复。
4. 如需清理 `app/data` 历史孤儿文件，先让用户确认保留策略，再按 DB 引用关系清理。

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
