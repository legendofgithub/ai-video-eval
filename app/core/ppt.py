# -*- coding: utf-8 -*-
"""AI-generated PPT deck evaluation: dimensions, local metrics, rendering, LMM scoring.

Mirrors the video side's design philosophy: heuristic local metrics where
determinism matters (P10), vision LLM where content understanding matters,
and graceful degradation when a slide renderer is unavailable.
"""
import glob
import json
import os
import re
import subprocess
import sys

from .logger import get_logger

log = get_logger("videoeval.ppt")

try:
    from pptx import Presentation
except ImportError:  # pragma: no cover - dependency declared in requirements
    Presentation = None  # type: ignore[assignment,misc]

DEFAULT_PPT_SPEC_ID = "spec_ppt_default_10"

PPT_DIMENSIONS: list[dict] = [
    {"dim_id": "P01", "name": "内容完整性", "layer": "content",
     "anchor_low": "缺少封面/目录/结尾等关键页，结构残缺",
     "anchor_mid": "结构基本完整，个别环节薄弱",
     "anchor_high": "封面、目录、章节、总结齐备，结构完整"},
    {"dim_id": "P02", "name": "逻辑连贯性", "layer": "content",
     "anchor_low": "页间跳跃混乱，章节编排无逻辑",
     "anchor_mid": "大体连贯，局部过渡生硬",
     "anchor_high": "叙事递进清晰，章节衔接自然"},
    {"dim_id": "P03", "name": "文本质量", "layer": "content",
     "anchor_low": "错别字/语病密集，表述含混",
     "anchor_mid": "偶有瑕疵，整体通顺",
     "anchor_high": "文字准确凝练，表达专业"},
    {"dim_id": "P04", "name": "信息真实性", "layer": "content",
     "anchor_low": "编造数据/虚构事实（AI 幻觉）频发",
     "anchor_mid": "个别数据存疑，无硬性事实错误",
     "anchor_high": "数据与事实可靠，无幻觉痕迹"},
    {"dim_id": "P05", "name": "排版质量", "layer": "design", "needs_render": True,
     "anchor_low": "元素错位/溢出/重叠，留白失控",
     "anchor_mid": "基本整齐，局部拥挤",
     "anchor_high": "对齐精良，留白从容，无溢出重叠"},
    {"dim_id": "P06", "name": "配色与可读性", "layer": "design", "needs_render": True,
     "anchor_low": "对比度差/字号过小，几乎不可读",
     "anchor_mid": "可读，配色平淡或局部刺眼",
     "anchor_high": "对比舒适，层级分明，观感专业"},
    {"dim_id": "P07", "name": "风格一致性", "layer": "design", "needs_render": True,
     "anchor_low": "字体/配色/版式页页不同，拼凑感强",
     "anchor_mid": "整体统一，个别页跑偏",
     "anchor_high": "母版风格贯穿全篇，浑然一体"},
    {"dim_id": "P08", "name": "主题符合度", "layer": "semantic",
     "anchor_low": "内容与生成要求严重不符",
     "anchor_mid": "主题相关但覆盖不全",
     "anchor_high": "精准回应生成要求，内容切题"},
    {"dim_id": "P09", "name": "受众与场景适配", "layer": "semantic",
     "anchor_low": "深浅失当，语言风格与用途错位",
     "anchor_mid": "基本适配，详略欠佳",
     "anchor_high": "详略得当，语言风格贴合用途"},
    {"dim_id": "P10", "name": "结构规范度", "layer": "spec", "metric": "local",
     "anchor_low": "文字密度过载/字号过小/字体混乱",
     "anchor_mid": "偶有拥挤或字号偏小",
     "anchor_high": "密度适中，字号规范，用字克制"},
]

PPT_DIM_IDS = [d["dim_id"] for d in PPT_DIMENSIONS]
RENDER_DIMS = {d["dim_id"] for d in PPT_DIMENSIONS if d.get("needs_render")}
LOCAL_PPT_DIMS = {"P10"}
# 低分门控映射（人工评分二期使用）：层 -> 门控类型
PPT_GATE_BY_LAYER = {"content": "content", "design": "technical",
                     "semantic": "semantic", "spec": "technical"}

MAX_RENDER_SLIDES = 16
SOFFICE_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def parse_deck(path):
    """Structural parse via python-pptx. Raises ValueError when unreadable."""
    if Presentation is None:
        raise ValueError("python-pptx 未安装")
    try:
        prs = Presentation(path)
    except Exception as e:
        raise ValueError(f"无法解析的 pptx：{e}") from e
    slides = []
    fonts = set()
    sizes = []
    for idx, slide in enumerate(prs.slides, start=1):
        title, chunks = "", []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = shape.text_frame.text.strip()
            if not text:
                continue
            if shape == slide.shapes.title and text:
                title = text
            chunks.append(text)
            for para in shape.text_frame.paragraphs:
                if para.font.size is not None:
                    sizes.append(para.font.size.pt)
                for run in para.runs:
                    if run.font.size is not None:
                        sizes.append(run.font.size.pt)
                    if run.font.name:
                        fonts.add(run.font.name)
        slides.append({"index": idx, "title": title,
                       "text": "\n".join(chunks)[:1200],
                       "chars": sum(len(c) for c in chunks)})
    width_in = prs.slide_width / 914400 if prs.slide_width else 10
    height_in = prs.slide_height / 914400 if prs.slide_height else 7.5
    return {"slide_count": len(slides), "slides": slides,
            "fonts": sorted(fonts), "sizes": sizes,
            "width_in": round(width_in, 2), "height_in": round(height_in, 2)}


def local_metrics(path):
    """P10 结构规范度: deterministic heuristics over the deck structure."""
    meta = parse_deck(path)
    slides = meta["slides"]
    if not slides:
        return {"value": None, "confidence": None, "note": "无幻灯片"}
    dense = [s for s in slides if s["chars"] > 800]
    dense_ratio = len(dense) / len(slides)
    min_size = min(meta["sizes"]) if meta["sizes"] else None
    small_ratio = (sum(1 for s in meta["sizes"] if s < 12) / len(meta["sizes"])
                   if meta["sizes"] else 0)
    font_count = len(meta["fonts"])
    score = 10.0
    score -= dense_ratio * 4
    if min_size is not None and min_size < 12:
        score -= 2
    score -= small_ratio * 2
    if font_count > 5:
        score -= min(2.0, (font_count - 5) * 0.4)
    score = round(max(0.0, min(10.0, score)), 2)
    note = (f"本地启发式: 页均密度过载 {len(dense)}/{len(slides)} 页, "
            f"最小字号 {min_size if min_size is not None else '默认(继承)'}, "
            f"字体 {font_count} 种")
    return {"value": score, "confidence": 0.8, "note": note}


_renderer_cache: dict | None = None


def detect_renderer() -> dict:
    """Probe for a slide renderer once per process. Returns backend info."""
    global _renderer_cache
    if _renderer_cache is not None:
        return _renderer_cache
    result: dict = {"backend": None, "detail": "未检测到 PowerPoint 或 LibreOffice"}
    if os.path.exists(r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE") \
            or os.path.exists(r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE"):
        try:
            import win32com.client  # noqa: F401
            result = {"backend": "powerpoint", "detail": "本机 PowerPoint"}
        except ImportError:
            result = {"backend": None, "detail": "检测到 PowerPoint 但缺少 pywin32"}
    else:
        for cand in SOFFICE_CANDIDATES:
            if os.path.exists(cand):
                result = {"backend": "libreoffice", "detail": "本机 LibreOffice"}
                break
    _renderer_cache = result
    return result


def render_slides(pptx_path, out_dir, timeout=180):
    """Render slides to PNGs in out_dir via an isolated subprocess.

    Returns sorted PNG paths, or None when no renderer is available.
    COM lives in a child process so its thread model never touches uvicorn.
    """
    backend = detect_renderer()
    if backend["backend"] is None:
        return None
    os.makedirs(out_dir, exist_ok=True)
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--render-child", pptx_path, out_dir]
    else:
        server_py = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "server.py")
        cmd = [sys.executable, server_py, "--render-child", pptx_path, out_dir]
    try:
        subprocess.run(cmd, timeout=timeout, capture_output=True, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as e:
        log.warning("slide render failed: %s", e)
        return None
    return normalize_slide_names(out_dir)


def _natural_key(path):
    digits = re.findall(r"(\d+)", os.path.basename(path))
    return int(digits[-1]) if digits else 0


def normalize_slide_names(out_dir):
    """Rename exported files (COM names them 幻灯片1.PNG etc.) to
    slide-NN.png in numeric order so serving/sampling stays stable."""
    pngs = (glob.glob(os.path.join(out_dir, "*.png"))
            + glob.glob(os.path.join(out_dir, "*.PNG")))
    for i, src in enumerate(sorted(set(pngs), key=_natural_key), start=1):
        target = os.path.abspath(os.path.join(out_dir, f"slide-{i:02d}.png"))
        if os.path.abspath(src) != target:
            os.replace(src, target)
    return sorted(glob.glob(os.path.join(out_dir, "slide-*.png")))


def run_render_child(pptx_path, out_dir):
    """Executed inside the isolated child process (see server __main__)."""
    backend = detect_renderer()["backend"]
    if backend == "powerpoint":
        _com_export(pptx_path, out_dir)
    elif backend == "libreoffice":
        _soffice_export(pptx_path, out_dir)
    else:
        raise RuntimeError("no renderer")
    normalize_slide_names(out_dir)


def _com_export(pptx_path, out_dir):
    import win32com.client
    app = win32com.client.Dispatch("PowerPoint.Application")
    pres = app.Presentations.Open(os.path.abspath(pptx_path),
                                  ReadOnly=True, Untitled=False, WithWindow=False)
    try:
        pres.Export(os.path.abspath(out_dir), "PNG", 1280, 720)
    finally:
        pres.Close()
        app.Quit()


def _soffice_export(pptx_path, out_dir):
    soffice = next(c for c in SOFFICE_CANDIDATES if os.path.exists(c))
    tmp_pdf_dir = os.path.join(os.path.dirname(out_dir), "_pdf")
    os.makedirs(tmp_pdf_dir, exist_ok=True)
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir",
         tmp_pdf_dir, os.path.abspath(pptx_path)],
        timeout=180, capture_output=True, check=True)
    import pypdfium2 as pdfium
    pdf_path = os.path.join(
        tmp_pdf_dir, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    pdf = pdfium.PdfDocument(pdf_path)
    try:
        for i in range(min(len(pdf), MAX_RENDER_SLIDES)):
            page = pdf[i]
            image = page.render(scale=1.5).to_pil()
            image.save(os.path.join(out_dir, f"slide-{i + 1:02d}.png"))
    finally:
        pdf.close()


def _chat_json(client, model, prompt, image_paths=None, temperature=0.0):
    """Call an OpenAI-compatible chat endpoint and parse strict-JSON scoring."""
    content = [{"type": "text", "text": prompt}]
    for img in image_paths or []:
        with open(img, "rb") as f:
            b64 = __import__("base64").b64encode(f.read()).decode("utf-8")
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})
    resp = client.chat.completions.create(
        model=model, temperature=temperature,
        messages=[{"role": "user", "content": content}])
    txt = resp.choices[0].message.content
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}
    try:
        val = float(obj.get("value", -1))
    except (TypeError, ValueError):
        return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}
    if not 0 <= val <= 10:
        return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}
    conf = min(1.0, max(0.0, float(obj.get("confidence", 0.5))))
    return {"value": round(val, 2), "confidence": round(conf, 2),
            "note": str(obj.get("note", ""))}


def build_dim_prompt(dim, outline_text=None, prompt_text=None, visual=False):
    p = (f"你是 AI 生成 PPT 的质量评测专家。请对这套幻灯片在维度「{dim['name']}」"
         f"({dim['dim_id']}, 层={dim['layer']}) 上打分。\n"
         f"0-10 分锚定：低分={dim['anchor_low']}；中分={dim['anchor_mid']}；"
         f"高分={dim['anchor_high']}。\n")
    if prompt_text and dim["dim_id"] in ("P08", "P09"):
        p += f"这套 PPT 的生成要求/主题是：{prompt_text}\n请据此判断贴合程度。\n"
    if outline_text and not visual:
        p += ("以下是全部幻灯片的大纲文本（每页含标题与正文节选）：\n"
              + outline_text + "\n")
    if visual:
        p += "以下是幻灯片页面截图，请基于你看到的视觉呈现评分。\n"
    p += ("仅输出 JSON，格式：{\"value\": <0-10数字>, \"confidence\": <0-1数字>, "
          "\"note\": \"<简短理由>\"}。不要输出任何其他文字。")
    return p


def _sample(paths, n=8):
    if len(paths) <= n:
        return paths
    step = len(paths) / n
    return [paths[int(i * step)] for i in range(n)]


def outline_text_of(meta, per_slide=200):
    lines = []
    for s in meta["slides"]:
        title = s["title"] or f"第{s['index']}页"
        body = s["text"].replace(title, "", 1).strip()[:per_slide]
        lines.append(f"第{s['index']}页 [{title}] {body}")
    return "\n".join(lines)


def evaluate_deck(pptx_path, dims, lmm_cfg=None, prompt_text=None,
                  slides_dir=None):
    """Score the requested dimensions. Per-dim failures never raise.

    P10 is computed locally; design dims require a slide renderer plus a
    vision model; content/semantic dims read the outline text (plus slide
    images when a renderer happens to be available).
    """
    results = {}
    meta = parse_deck(pptx_path)
    local = [d for d in dims if d["dim_id"] in LOCAL_PPT_DIMS]
    for d in local:
        results[d["dim_id"]] = local_metrics(pptx_path)

    lmm_dims = [d for d in dims if d["dim_id"] not in LOCAL_PPT_DIMS]
    if not lmm_dims:
        return results

    render_dims = [d for d in lmm_dims if d.get("needs_render")]
    text_dims = [d for d in lmm_dims if not d.get("needs_render")]

    lmm_ok = bool(lmm_cfg and lmm_cfg.get("base_url") and lmm_cfg.get("api_key")
                  and lmm_cfg.get("model"))
    client = None
    if lmm_ok:
        from openai import OpenAI
        client = OpenAI(base_url=lmm_cfg["base_url"],
                        api_key=lmm_cfg["api_key"], timeout=90)

    outline = outline_text_of(meta)

    # Renderer is a design dim's first prerequisite: report it before the
    # model config so the fix-the-renderer message never gets masked.
    slide_images = None
    if render_dims:
        if not detect_renderer()["backend"]:
            for d in render_dims:
                results[d["dim_id"]] = {"value": None, "confidence": None,
                                        "note": "NO_RENDERER"}
            render_dims = []
        else:
            if slides_dir is None:
                slides_dir = os.path.join(
                    os.path.dirname(pptx_path),
                    os.path.splitext(os.path.basename(pptx_path))[0] + "_slides")
            slide_images = render_slides(pptx_path, slides_dir)
            if not slide_images:
                for d in render_dims:
                    results[d["dim_id"]] = {"value": None, "confidence": None,
                                            "note": "NO_RENDERER"}
                render_dims = []

    for d in text_dims:
        if not lmm_ok:
            results[d["dim_id"]] = {"value": None, "confidence": None,
                                    "note": "未配置视觉模型"}
            continue
        try:
            results[d["dim_id"]] = _chat_json(
                client, lmm_cfg["model"],
                build_dim_prompt(d, outline_text=outline, prompt_text=prompt_text),
                temperature=lmm_cfg.get("temperature", 0.0))
        except Exception as e:
            log.warning("deck dim %s failed: %s", d["dim_id"], e)
            results[d["dim_id"]] = {"value": None, "confidence": None,
                                    "note": f"LMM_ERROR: {e}"}

    for d in render_dims:
        if not lmm_ok:
            results[d["dim_id"]] = {"value": None, "confidence": None,
                                    "note": "未配置视觉模型"}
            continue
        try:
            results[d["dim_id"]] = _chat_json(
                client, lmm_cfg["model"],
                build_dim_prompt(d, prompt_text=prompt_text, visual=True),
                image_paths=_sample(slide_images),
                temperature=lmm_cfg.get("temperature", 0.0))
        except Exception as e:
            log.warning("deck dim %s failed: %s", d["dim_id"], e)
            results[d["dim_id"]] = {"value": None, "confidence": None,
                                    "note": f"LMM_ERROR: {e}"}
    return results
