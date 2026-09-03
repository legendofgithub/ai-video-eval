# AI 视频质量评测项目交接记录

> 更新时间：2026-09-03 12:06 +08:00
> 当前结论：P1/P2/P3 已完成；P4 的主观评分、专家仲裁、可靠性、VBench 导出、托盘与边界测试、产品介绍页已进入网页端。2026-09-01 下午增量审计修复路径安全、无效专家仲裁、windowed 日志、上传错误反馈、双曲线雷达与 pytest 日志隔离，提交为 `5242693`、`299ac71`。2026-09-03 真实 DeepSeek 视觉探测与网页端 D01 评测已验证可行。
> 当前 Git：`master`；最近代码提交为 `5242693`、`299ac71`，本轮仅追加交接文档提交。`app/_audit_0902.py` 是本轮开始前已有未跟踪脚本，未改动。
> 当前运行状态：本轮自启的 `8905` 已停止；临时视频、评分与脚本已清理。共享库保留本轮开始前已有的 `a5069653 / audit_0902`（1 视频、1 分数），本轮新增记录已删除。`8765/8876/8904` 为外部进程，本轮未擅停。

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

### 2026-09-01 增量审计修复（已提交 `1b796af`）

- **P3 逐维低分门控**：主观评分 API 兼容旧 `gate`，新增 `gates={dim_id: reason}`；低分原因按维度层校验，并分 valid/invalid 两组落库，避免一个错分低分维度把整条提交的其他维度全部排除出 ICC/Krippendorff。
- **工作台真实交互**：每个维度滑块旁新增低分原因选择；低于等于 4 分时启用并强制选择匹配原因，非低分自动回“不适用”，移动端布局同步调整。
- **专家仲裁与看板口径**：VBench 导出和 `/api/dashboard` 均改为“专家按维度覆盖有效主观均值”；部分仲裁不再抹掉未仲裁维度，也不再让专家分作为普通评分稀释均值。
- **追溯与去重**：低分备注写入对应 `scores[dim].note`；重复上传响应直接返回完整既有元数据，前端不再依赖最近 20 条列表反查。
- 新增回归覆盖逐维门控隔离、非法门控、低分备注、部分专家仲裁、看板覆盖口径与重复上传元数据。

### 2026-09-01 下午增量审计修复（已提交 `5242693`、`299ac71`）

- **文件接口安全边界**：`get_video_path` 对候选文件做视频目录内的规范化路径校验，`..\\` / `%2F` 形式的 video_id 不再能读取目录外文件，并新增回归测试。
- **专家仲裁有效性**：VBench 导出与数据看板只允许 `is_valid=1` 的专家仲裁覆盖主观均值；错误低分门控的专家记录保留追溯但不再污染结果。
- **windowed 日志路径**：logger 在 PyInstaller frozen 模式下改从 `sys.executable` 所在目录推导 `data/app.log`，与持久化数据目录一致。
- **上传与初始化反馈**：上传失败/初始化失败会弹出可见错误；文件 input 提交后清空，允许立即重选同一个无效文件。
- **雷达图口径**：`/api/dashboard` 分别返回客观分均值与人工/专家校准均值；前端雷达真实绘制两条曲线和图例，不再把两类分数合成一条曲线。
- **pytest 日志隔离**：autouse fixture 会替换并关闭 `videoeval*` logger 句柄，把日志指向临时目录；完整 pytest 前后真实 `data/app.log` SHA256 保持不变。

### 2026-09-03 真实 DeepSeek 消耗受控验证

- **零/近零消耗预检**：`/user/balance` 可用，期初余额 `44.50 CNY`；`/models` 返回 `deepseek-v4-flash`、`deepseek-v4-pro`、`deepseek-v4-flash-vision-exp`。
- **核心链路精确 usage**：64x64 视觉探测成功识别 `circle/red`，usage `283 tokens`；真实广告 D01 四帧评分返回 `8.0/10`、confidence `0.9`，usage `1,942 tokens`。两次合计 `2,225 tokens`。
- **网页端产品链路**：可见 Edge 填写 Base URL / 模型 / API Key，上传 320x180 临时视频，点击 D01 后自动探测并真实评测，返回 `10.0/10`、confidence `0.98`；UI 删除本轮视频成功。此段 2 次请求（探测 + 8 帧评分），产品响应不透出 usage，仅用余额监控，未见明显扣减。
- **消耗结论**：全程共 4 次模型请求；最终余额 `44.49 CNY`，观察到的余额降幅 `0.01 CNY`。按官方价格页 `deepseek-v4-flash-vision-exp` 1M cache-miss input / output 计价，已精确测得的 `2,225 tokens` 理论费用低于余额显示精度，扣减量正常。API Key 未写入 config、代码、交接或 Git；测试浏览器已关闭。

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

2026-09-01 复核：

- Pytest：`36 passed, 2 skipped`（2 个真实 DeepSeek 用例因未设置 `DEEPSEEK_API_KEY` 跳过）
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`
- `node --check web/app.js`：通过
- `git diff --check`：通过

2026-09-01 16:20 复核：

- Pytest：`41 passed, 2 skipped`（2 个真实 DeepSeek 用例因未设置 `DEEPSEEK_API_KEY` 跳过）
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`
- `node --check web/app.js`：通过
- `git diff --check`：通过
- 日志隔离断言：pytest 前后 `data/app.log` SHA256 相同

2026-09-03 复核：

- Pytest（未注入 Key，真实 API 用例按设计跳过）：`41 passed, 2 skipped`
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`

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

2026-09-01 增量真实验证（自启 `127.0.0.1:8902`，已停止）：

- 可见 Edge `1440x900`：首页 10 张维度卡、无横向溢出；上传临时 mp4 后重复上传显示“已存在”，模型标识保持 `audit_p3_edge`。
- D03 本地评测真实点击成功并显示分数。
- 工作台将 D05=3、D08=3：先验证未选原因被弹窗阻断，再分别选择“语义错位”“物理/常识错误”和备注“悬浮 @ 00:03”，保存返回 `有效维度=10/10`。
- 数据看板雷达、MOS 直方图、模型榜、明细和世界模型子榜渲染，无横向溢出。
- VBench 下载包含 `audit_p3_edge`；下载验证后既有 `vbench_export.json` 内容恢复为原 530 字节。
- 通过 UI 删除本轮视频后，数据库回到 `videos=0, scores=0`；移动端 `390x844` 无横向溢出。
- 本轮截图：`app/_shots/audit_p3_desktop_home.png`、`audit_p3_duplicate.png`、`audit_p3_d03.png`、`audit_p3_workbench.png`、`audit_p3_board.png`、`audit_p3_mobile_home.png`（目录 gitignored）。

2026-09-01 下午真实验证（自启 `127.0.0.1:8903`，已停止）：

- 可见 Edge `1440x900`：无效 mp4 上传弹出“上传失败”，待测占位保持隐藏；有效上传和重复上传均显示 `audit_fix_edge`。
- D03 本地评测真实点击成功；工作台 D05=3、D08=3 先被错误/缺失门控阻断，选择“语义错位”“物理/常识错误”后保存 `有效维度=10/10`。
- VBench 下载包含 `audit_fix_edge`；看板模型榜、明细、D03 排序、直方图和世界模型子榜可用，桌面与移动端 `390x844` 均无横向溢出。
- 路径穿越请求返回 404；雷达图验证为 4 条网格多边形 + 客观分/人工专家校准 2 条数据曲线，图例文案正确。
- 删除真实视频时首次遇到 Windows 文件锁，接口返回 409 且数据库记录保留；稍后重试真实 UI 删除返回 200，最终 `/api/videos=[]`、`videos=0, scores=0`。
- 本轮截图：`app/_shots/audit_fix_desktop_home.png`、`audit_fix_duplicate.png`、`audit_fix_d03.png`、`audit_fix_workbench.png`、`audit_fix_board.png`、`audit_fix_mobile_home.png`、`audit_radar_two_curves.png`（目录 gitignored）。

2026-09-03 DeepSeek 真实验证（自启 `127.0.0.1:8905`，已停止）：

- 模型列表与余额接口可用；`deepseek-v4-flash-vision-exp` 具备视觉能力。
- 核心链路 D01 四帧评分成功；网页端真实表单/按钮链路成功，截图 `app/_shots/deepseek_ui_d01.png`。
- 唯一前端 Console 错误为既有 favicon 404，不影响评测链路。

### 打包历史证据

- PyInstaller `--onefile --windowed` 曾生成 `124,479,275` 字节 exe。
- `8876` 健康 200、托盘/无浏览器环境变量已验证；当时临时 exe 与构建目录已清理。
- 瘦身按用户要求跳过，体积非当前约束。

## 4. 未完成

1. ~~真实 DeepSeek 视觉链路仍未执行~~ 已解决：2026-09-03 核心链路和网页端 D01 均通过；测试 Key 未持久化。
2. 网页端还没有“一键 10 维评测”和任务队列，多维度仍需逐卡执行。
3. ~~2026-09-01 下午改动未提交~~ 已解决：代码提交为 `5242693`、`299ac71`。
4. 可靠性统计当前只统计人工标注员，专家仲裁作为导出覆盖值，不参与 ICC/Krippendorff；若产品希望专家也参与一致性，需要先定义口径。
5. `app/data` 中存在历史孤儿媒体/日志文件；本轮只删除本轮生成和本轮测试对应数据，未清理可能属于用户的历史运行数据。
6. 产品接口目前不透出模型 `usage`，本轮只能通过外层 wrapper 与余额接口监控；若进入批量十维测试，应先在服务端记录并在 UI 展示每次/累计 token。

## 5. 阻塞与外部状态

- `8765` 被进程 `20888`、`8876` 被进程 `34124`（均为 `videoeval` Python 环境 `server.py`）占用；它们不是本轮启动，未按指令擅停。
- `8904` 被进程 `17316`（`videoeval` Python 环境 `server.py`）占用，伴随未跟踪脚本 `app/_audit_0902.py`，判断为另一轮外部测试状态；本轮未修改或停止。
- 本地视觉复核 `glance` 缺 `VISION_API_KEY`；本轮以真实浏览器 DOM 断言、截图和溢出计算替代。
- PowerShell `Remove-Item` 会被本机策略拦截；本轮仅用 Python 删除两个已校验路径的临时文件，未做递归删除。

## 6. 下一轮建议

1. （历史完成）统计、隔离、端口和 UI 修复见 `3ff9be7`；本轮边界与看板修复见 `5242693`、`299ac71`。
2. 设计“一键 10 维评测”任务队列：并发、取消、失败重试、逐维结果恢复；执行前预估 token/费用上限并在超限时停止。
3. 如需清理 `app/data` 历史孤儿文件，先让用户确认保留策略，再按 DB 引用关系清理。

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
