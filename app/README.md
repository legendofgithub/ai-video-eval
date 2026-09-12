# AI 视频质量评测工具 — 运行与打包说明

## 本地运行（方式一：源码 + 一键脚本）
1. 本机安装 Python 3.11+
2. 双击 `run.bat`（Windows）或执行：
   ```
   pip install -r requirements.txt
   python app.py
   ```
3. 浏览器自动打开 `http://localhost.7860`

## 分发网页版（方式二：PyInstaller 单 exe）
构建命令（在 app/ 目录）：
```
pip install pyinstaller pystray Pillow
pyinstaller --noconfirm --onefile --windowed --name VideoEvalWeb --add-data "web;web" --hidden-import pystray --collect-all pystray --collect-all pptx --hidden-import win32com.client server.py
```
产物在 `dist/VideoEvalWeb.exe`（约 120MB），拷贝到目标机器后双击运行，约 2 秒后自动打开浏览器进入界面；重复双击会直接打开已运行实例的界面；8765 被其它程序占用时自动顺延 8766+。任务栏托盘图标提供「打开浏览器」（重复打开用）和「退出」。评测数据全部保存在 exe 同目录唯一的 `data/` 文件夹内（`evaluation.db`、`config.json`、视频、抽帧与日志；旧版散落在外的那两个文件会在首次启动时自动移入）；删除 `data/` 文件夹即完全重置。运行日志写入 `data/app.log`。

自动化验证时可设置 `VIDEOEVAL_NO_BROWSER=1` 禁止自动开浏览器，设置 `VIDEOEVAL_PORT=8876` 指定备用端口。
> 注意：打包后体积较大（约百余 MB），属正常。接收方无需装 Python。
> 分发压缩包严禁携带 `config.json`、`evaluation.db`、`data/` 与任何测试脚本：它们可能包含你的 API Key、评测记录和视频数据。

## LMM 自动评测配置（在「⑥ 设置」页填写）
- **本地 Ollama + DeepSeek-VL2**（推荐零成本）：
  base_url=`http://localhost:11434/v1`，api_key=`ollama`，model=`deepseek-vl2`
  先 `ollama pull deepseek-vl2` 并 `ollama serve`
- **GPT-4o**：base_url=`https://api.openai.com/v1`，api_key=你的 key，model=`gpt-4o`
- **Gemini**：base_url=`https://generativelanguage.googleapis.com/v1beta/openai/`，api_key=你的 key，model=`gemini-2.0-flash`
- **DeepSeek 视觉**：base_url=`https://api.deepseek.com/v1`，api_key=你的 key，model=`deepseek-v4-flash-vision-exp`
> 评测对象为「AI 生成的视频」本身。DeepSeek 官方已于 2026 年提供视觉模型 `deepseek-v4-flash-vision-exp`（经实测可用），非仅文本 V3/R1；本地零成本方案仍可用 Ollama + DeepSeek-VL2。

## 评测流程
1. ① 上传视频（填 prompt 与模型标识）
2. ② 选维度 → 运行 LMM 自动打分（客观分）
3. ③ 人工标注台：逐维 0-10 打锚定分，低分做「技术/物理/语义」门控
4. ④ 争议视频送专家仲裁
5. ⑤ 看板：雷达图 / 模型对比 / ICC 一致性 / 导出 VBench JSON

## 可视化网页前端（新版）
1. 双击 `run_web.bat`（或执行 `python server.py`）
2. 浏览器打开 `http://127.0.0.1:8765`
3. 主页「待测试区」上传视频；「测试用模型面板」填写视觉模型 API 并检测视觉能力
4. 点击任意维度卡片逐维测试；或点「一键完成测评」一次跑完全部十维（D03/D04 本地，8 维连续调用视觉模型，约 1-2 分钟），点「归档测评结果」把快照存入「测评档案」页（本机 SQLite，重开应用仍在）
5. 「评分工作台」内置视频播放器：支持 0.25×–2× 倍速、按视频真实帧率逐帧步进、「打点 @ mm:ss」把当前时间戳插入低分备注（配合 SOP「违规类型 @ mm:ss」格式）
6. 「PPT 评测」页：上传 AI 生成的 .pptx，按 P01–P10 十维评测。P10 结构规范度本地免费；内容/语义维度由大模型读取大纲文本；设计维度（P05–P07）需先渲染幻灯片——本机装有 PowerPoint 或 LibreOffice 时自动启用（COM 渲染在隔离子进程执行），否则优雅降级不可用
7. 顶部切换「数据看板」查看雷达图、MOS 分布、模型榜、视频明细和世界模型子榜

> 提示：API Key 仅保存在当前浏览器会话中，服务端不落盘。

## 安全与开发规范
- 精确复现环境用 `pip install -r requirements.lock`；`requirements.txt` 仅声明最低版本。
- API Key 只通过界面「⑥ 设置」或环境变量 `DEEPSEEK_API_KEY` 注入，严禁写入代码、config 示例或提交到版本库。
- 克隆本仓库后先复制 `config.example.json` 为 `config.json`，再按需填写本地配置。
- `config.json`、`evaluation.db`、`data/`、`测试用例/` 已在 `.gitignore` 中排除，属于本机运行数据。
- 提交前自查：`rg -n "sk-" app/` 应无任何真实 Key 命中。
