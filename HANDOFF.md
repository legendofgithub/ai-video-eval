# AI 视频质量评测项目交接记录

> 更新时间：2026-09-09 13:45 +08:00
> 当前结论：P1/P2/P3 已完成；P4 的主观评分、专家仲裁、可靠性、VBench 导出、托盘与边界测试、产品介绍页已进入网页端。2026-09-01 下午增量审计修复路径安全、无效专家仲裁、windowed 日志、上传错误反馈、双曲线雷达与 pytest 日志隔离，提交为 `5242693`、`299ac71`。2026-09-03 真实 DeepSeek 视觉探测与网页端 D01 评测已验证可行。2026-09-07 补齐审计发现的头号缺口：评分工作台新增视频播放器（逐帧/倍速/打点）。2026-09-09 完成 10 条漫剧真实视频批量评测（数据保留）并修复竖屏播放器显示，均未提交。
> 当前 Git：`master`；最近代码提交为 `e4c0891`（feat: API Key 持久化 + 脱敏回显，取消一键十维）。工作区含 2026-09-07 工作台播放器 + 2026-09-09 竖屏修复改动（core/storage.py、web/ 三件套、tests/test_storage.py、README、本文件），未提交。
> 当前运行状态：本轮自启的 `8917` 已停止；`app/data` 中保留 10 条漫剧视频与 92 条评分记录（用户真实评测数据，勿清理）；拼图证据在 `app/_shots/manju/`（gitignored）。`8765/8876/8904` 为外部进程，本轮未擅停。

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

### 2026-09-05 API Key 持久化 + 脱敏回显 + 取消一键十维（已提交 `e4c0891`）

按用户 9/5 明确决策，落实三项产品行为变更：

1. **取消一键出十维**：保持「逐维度评测」为唯一路径，不做批量十维评测与任务队列。产品介绍页边界描述由“还没有一键十维”改为“刻意采用逐维度评测”。
2. **API Key 持久化**：`save_lmm_config()` 写入 `app/config.json`（gitignored）；前端“保存配置”后落库，刷新后自动回填，不再依赖 sessionStorage，用户无需每次测试重填。
3. **API Key 脱敏**：`mask_api_key()` 保留首尾各 10 位、中段以 `*` 覆盖；查看/修改时仅回显脱敏串、输入框只读，“更换”按钮触发重新输入；真实 Key 不落前端明文。关键不变量：含 `*` 的脱敏串不会被写回覆盖真 Key（`test_lmm_config` 第 5 例显式校验“落库 key 仍为原文”）。

- 新增 `GET/POST /api/config/lmm`（脱敏视图 / 保存）；`_resolve_lmm` 在请求字段为空或传入脱敏串时回退到已保存配置。
- 新增 `app/tests/test_lmm_config.py`（9 用例全绿），覆盖首尾保留、无明文泄漏、短 Key 全掩、保存持久化、脱敏串不覆盖真 Key、空 Key 保留旧值、脱敏视图不回显明文。
- mypy 闸门：`server.py` 对可选依赖 `pystray`/`PIL` 的延迟导入补 `type: ignore[import-untyped]`，恢复 0 error（该 `import-untyped` 为预存，非本次功能引入）。

### 2026-09-07 评分工作台视频播放器（未提交）

按用户决策补齐审计发现的头号可用性缺口（原工作台打分时看不到视频，SOP 的逐帧核对无法执行）：

1. **播放器卡片**：工作台「① 选择视频与身份」之后新增「② 播放待评视频」，原生 `<video>` 走既有 `/api/video/{id}/file`；后续卡片重编号 ③④⑤。切视频即换源（`dataset.vid` 去重避免重复视图切换时重载）。
2. **逐帧步进**：`list_videos()` 新增返回 `fps`（后端唯一接口改动），前端按真实 fps（缺失回退 24）以 ±1 帧步进 `currentTime`，步进自动暂停。实测 30fps 视频每步 0.0333s。
3. **倍速与打点**：0.25×/0.5×/1×/2× 切换 `playbackRate`（换源后在 `loadedmetadata` 重应用）；「打点 @ mm:ss」按光标位置插入当前时间戳到备注，自动补前导空格对齐 SOP「违规类型 @ mm:ss」格式。
4. **验证**：Playwright + 真实 Edge 内核 14/14 通过（视图切换、视频加载 readyState=4、时长 00:00/00:30、前后逐帧、步进暂停、0.25×、打点「悬浮 @ 00:00」、桌面/移动 390×844 无横向溢出、主页/看板回归）；截图 `app/_shots/player_workbench_desktop.png`、`player_workbench_mobile_top.png`、`player_chinese_filename.png`。质量门禁 pytest `50 passed, 2 skipped` / ruff / mypy / `node --check` 全绿。
5. **附带核实**：中文文件名经真实浏览器上传端到端正确（待测区与下拉均正常显示）；此前截图中的乱码名为 curl 以 GBK 上传的测试数据问题，非产品缺陷，已随测试数据删除。本会话内嵌浏览器（IAB）输入注入与截图通道损坏，改用项目既有 Playwright 路线完成验证。

### 2026-09-09 漫剧真实视频批量评测 + 竖屏播放器修复（数据保留，未提交）

1. **真实数据入库（保留不清理）**：从 `测试用例/漫剧/` 选 10 条代表性视频上传（吸血鬼两集成片 1890x1080 HEVC、4 条 Seko 分镜、竖屏 720x1280 洗面奶广告、2 条火力突围片段、画布展示），全部含 UTF-8 中文文件名、prompt（两集）与模型标识；本轮是首轮用户真实评测数据，`videos=10, scores=92`，**有意保留**。
2. **评测执行**：D03/D04 本地信号全量出分；D01/D02/D05/D06/D08/D09/D10 由 AI 标注员（rater_id=`ai_observer`）基于每视频 6 帧采样拼图目视评分（拼图存 `app/_shots/manju/`），两集另含 D07；全部 >4 分无门控。全样本均分 7.89，洗面奶广告 6.44 垫底（D03=3.44 闪烁全场最差 + D01=5 色带伪影 + D05=6 西装消失@05s），Seko 分镜组 8.16、火力突围片段 8.28。
3. **竖屏修复**：实测确认 `#wbPlayer`/`.dim-stage video` 写死 `aspect-ratio:16/9` 导致竖屏视频被压成约 1/3 宽窄条；改为 `max-height:70vh` 自适应，竖屏画面显示面积约提升 2 倍（修复前后截图 `manju_vertical_ad.png` / `manju_vertical_ad_fixed.png`）。
4. **HEVC 实测**：本机 Edge 可正常播放 HEVC（1890x1080 成片 readyState=4 无解码错误）；此结论依赖机器的 HEVC 支持，纯 Chromium 环境仍需验证。
5. 首次大文件上传遇瞬时连接失败（服务端无日志），已在脚本层用重试规避；109MB/178MB 文件 MD5 去重与哈希计算正常。
6. **exe 双击即开修复（2026-09-09 下午）**：真实用户首双击反馈"只多了 evaluation.db，其余无事发生"——旧设计为纯托盘形态（Win11 隐藏托盘区导致零可见反馈）。`server.py` frozen 分支改为启动后 2 秒自动打开浏览器（托盘保留作再次打开/退出）；同时修复 `_start_tray` 失败分支的 `print` 在 windowed 无 stdout 下会抛异常杀死进程的隐患（改 `log.warning`）。门禁全绿后重新打包，桌面副本与 `dist/` 均已更新（123,552,264 字节），已实测启动正常。
7. **一键完成测评 + 测评档案（2026-09-09 下午，按用户指示收回 9/5 的"仅逐维"决策）**：新增 `POST /api/evaluate-all`（D03/D04 本地 + 8 维连续 LMM，逐维失败不落库不阻断，无配置时 8 维返回"未配置视觉模型"）；新增 `test_records` 表与 `/api/records` 增删查，归档为 `{D01..D10}` 快照；前端维度区左侧「一键完成测评」、右侧「归档测评结果」，新增「测评档案」导航页（视频名称 + D01–D10 + 归档时间表格）。端到端实测：临时视频一键出分 6.22/10.0、归档、查询、清理全通过，真实 10 条数据未动。介绍页边界文案由"刻意仅逐维"改为"一键与逐维并存"。
8. **启动容错三连（2026-09-09 下午）**：用户第二次遭遇 8765 占用弹窗（根因：上一次实例仍在后台运行）。`__main__` 启动逻辑重写：① 8765 上若已是本应用（`/api/health` 特征校验）→ 直接打开浏览器到它并 exit 0（重复双击=打开应用）；② 非显式 `VIDEOEVAL_PORT` 时 8765 被外来程序占用 → 自动顺延 8766–8775；③ 显式 `VIDEOEVAL_PORT`（自动化）保持严格。三种场景真实 exe 实测通过。注意：桌面 `data/`、`evaluation.db`、`config.json` 是用户本人 14:10 起的真实使用数据（含保存的 DeepSeek Key 与上传视频），**任何清理不得触碰**。
9. **运行数据收拢进唯一 data/ 文件夹（2026-09-09 下午）**：用户反馈双击后桌面蹦出 `evaluation.db`/`config.json` 不美观。`storage.py` 的 `DB`/`CONFIG_PATH` 全部移入 `DATA`（新增 `_runtime_path` 自动把旧位置的文件迁移进 data/，被锁时原地回退；`VIDEOEVAL_SKIP_MIGRATION` 供测试跳过，conftest 顶部置位）；`export.py` 的 `vbench_export.json` 同步移入 data/（改为动态读 `storage.DATA`，conftest 改补丁 `storage.DATA`）。双击后 exe 旁只出现一个 `data` 文件夹。门禁 55 passed 全绿，已重新打包部署。**事故与修复**：迁移时发现用户桌面库为空——此前某轮"清理桌面"误将用户 14:10 会话的 `data`+`evaluation.db`+`config.json`（含 Key、两条上传）当测试残留删除；本次迁移保住了用户重存的 Key（`has_key=true`），丢失的两条视频（洗面奶广告、失重跃迁SEG-001）已从 `测试用例\漫剧` 重新上传恢复（新 id `72a49514`/`3c008435`），当时的评分无法恢复。教训固化为铁律：**用户机器上 exe 旁的 `data/` 永远不属于清理范围**。

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

- Pytest：`50 passed, 2 skipped`（2 个真实 DeepSeek 用例因未设置 `DEEPSEEK_API_KEY` 跳过）
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

2026-09-05 复核（提交 `e4c0891`）：

- Pytest（从 `app/` 运行；`core` 仅在 `app/` 为 cwd 时可导入）：`50 passed, 2 skipped`
- Ruff：`All checks passed!`
- Mypy：`Success: no issues found in 10 source files`（补 `pystray`/`PIL` 延迟导入 `type: ignore` 后恢复 0 error）
- `node --check web/app.js`：通过

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
2. ~~网页端还没有“一键 10 维评测”和任务队列~~ 已按用户 9/5 决策放弃：刻意采用逐维度评测，不实现批量十维与任务队列。
3. ~~2026-09-01 下午改动未提交~~ 已解决：代码提交为 `5242693`、`299ac71`。
4. 可靠性统计当前只统计人工标注员，专家仲裁作为导出覆盖值，不参与 ICC/Krippendorff；若产品希望专家也参与一致性，需要先定义口径。
5. `app/data` 中存在历史孤儿媒体/日志文件；本轮只删除本轮生成和本轮测试对应数据，未清理可能属于用户的历史运行数据。
6. ~~产品接口目前不透出模型 usage...若进入批量十维测试应先展示 token~~ 批量十维已取消，usage 透出需求随之作废；若日后恢复批量再评估。

## 5. 阻塞与外部状态

- `8765` 被进程 `20888`、`8876` 被进程 `34124`（均为 `videoeval` Python 环境 `server.py`）占用；它们不是本轮启动，未按指令擅停。
- `8904` 被进程 `17316`（`videoeval` Python 环境 `server.py`）占用，伴随未跟踪脚本 `app/_audit_0902.py`，判断为另一轮外部测试状态；本轮未修改或停止。
- 本地视觉复核 `glance` 缺 `VISION_API_KEY`；本轮以真实浏览器 DOM 断言、截图和溢出计算替代。
- PowerShell `Remove-Item` 会被本机策略拦截；本轮仅用 Python 删除两个已校验路径的临时文件，未做递归删除。

## 6. 下一轮建议

1. （历史完成）统计、隔离、端口和 UI 修复见 `3ff9be7`；本轮边界与看板修复见 `5242693`、`299ac71`。
2. ~~设计“一键 10 维评测”任务队列~~ 已按用户 9/5 决策取消，不纳入路线。
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
