# AI 视频质量评测工具 — 运行与打包说明

## 本地运行（方式一：源码 + 一键脚本）
1. 本机安装 Python 3.11+
2. 双击 `run.bat`（Windows）或执行：
   ```
   pip install -r requirements.txt
   python app.py
   ```
3. 浏览器自动打开 `http://localhost.7860`

## 分发给他人（方式二：PyInstaller 单 exe）
构建命令（在 app/ 目录）：
```
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name VideoEval app.py
```
产物在 `dist/VideoEval.exe`，拷贝 + 解压即双击运行（自动起 localhost 并开浏览器）。
> 注意：Gradio 打包后体积较大（约数百 MB），属正常。接收方无需装 Python。
> 分发压缩包严禁携带 `config.json`、`evaluation.db`、`data/` 与任何测试脚本：它们可能包含你的 API Key、评测记录和视频数据。

## LMM 自动评测配置（在「⑥ 设置」页填写）
- **本地 Ollama + DeepSeek-VL2**（推荐零成本）：
  base_url=`http://localhost:11434/v1`，api_key=`ollama`，model=`deepseek-vl2`
  先 `ollama pull deepseek-vl2` 并 `ollama serve`
- **GPT-4o**：base_url=`https://api.openai.com/v1`，api_key=你的 key，model=`gpt-4o`
- **Gemini**：base_url=`https://generativelanguage.googleapis.com/v1beta/openai/`，api_key=你的 key，model=`gemini-2.0-flash`
> 评测对象为「AI 生成的视频」本身。DeepSeek 官方文本 API(V3/R1) 无视觉能力，须用 VL2 视觉模型。

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
4. 点击任意维度卡片开始测试：D03 / D04 本地出分，其余 8 维调用视觉大模型

> 提示：API Key 仅保存在当前浏览器会话中，服务端不落盘。

## 安全与开发规范
- API Key 只通过界面「⑥ 设置」或环境变量 `DEEPSEEK_API_KEY` 注入，严禁写入代码、config 示例或提交到版本库。
- 克隆本仓库后先复制 `config.example.json` 为 `config.json`，再按需填写本地配置。
- `config.json`、`evaluation.db`、`data/`、`测试用例/` 已在 `.gitignore` 中排除，属于本机运行数据。
- 提交前自查：`rg -n "sk-" app/` 应无任何真实 Key 命中。
