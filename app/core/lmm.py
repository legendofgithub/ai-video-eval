# -*- coding: utf-8 -*-
"""OpenAI-compatible vision LMM calls: per-dimension scoring and probing."""
import base64
import io
import json
import re

from openai import OpenAI
from PIL import Image, ImageDraw

from .logger import get_logger
from .media import frame_to_b64

log = get_logger("videoeval.lmm")


def build_dim_prompt(dim, prompt_text=None):
    p = (f"你是 AI 视频质量评测专家。请对这段 AI 生成的视频在维度「{dim['name']}」"
         f"({dim['dim_id']}, 层={dim['layer']}) 上打分。\n"
         f"0-10 分锚定：低分={dim['anchor_low']}；中分={dim['anchor_mid']}；"
         f"高分={dim['anchor_high']}。\n")
    if dim["dim_id"] == "D07" and prompt_text:
        p += f"该视频的生成文本提示(prompt)是：{prompt_text}\n请判断视频是否精准还原该提示。\n"
    p += ("仅输出 JSON，格式：{\"value\": <0-10数字>, \"confidence\": <0-1数字>, "
          "\"note\": \"<简短理由或违规描述>\"}。不要输出任何其他文字。")
    return p


def score_one_dim(client, model, dim, frame_paths, prompt_text, temperature):
    content = [{"type": "text", "text": build_dim_prompt(dim, prompt_text)}]
    for fp in frame_paths:
        b64 = frame_to_b64(fp)
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    try:
        resp = client.chat.completions.create(
            model=model, temperature=temperature,
            messages=[{"role": "user", "content": content}])
        txt = resp.choices[0].message.content
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            obj = json.loads(m.group(0))
            val = float(obj.get("value", -1))
            confidence = round(
                min(1.0, max(0.0, float(obj.get("confidence", 0.5)))), 2)
            if 0 <= val <= 10:
                return {"value": round(val, 2),
                        "confidence": confidence,
                        "note": str(obj.get("note", ""))}
    except Exception as e:
        return {"value": None, "confidence": None, "note": f"LMM_ERROR: {e}"}
    return {"value": None, "confidence": None, "note": "LMM_PARSE_FAIL"}


def _vision_test_image():
    """64x64 red circle PNG as a base64 data URL."""
    img = Image.new("RGB", (64, 64), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=(230, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def probe_vision(base_url, api_key, model):
    """Return {has_vision, reply/reason}: send a red circle and require the
    model to name both shape and color via strict JSON when possible."""
    if not (base_url and api_key and model):
        return {"has_vision": False, "reason": "配置不完整"}
    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=60)
        content = [
            {"type": "text", "text":
                '请看这张图片，仅输出 JSON：{"shape": "<形状>", "color": "<颜色>"}，'
                "不要输出其他文字。"},
            {"type": "image_url", "image_url": {"url": _vision_test_image()}},
        ]
        resp = client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "user", "content": content}])
        txt = (resp.choices[0].message.content or "").strip()
        shape, color = "", ""
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                shape = str(obj.get("shape", "")).lower()
                color = str(obj.get("color", "")).lower()
            except json.JSONDecodeError:
                pass
        # Fallback keyword matching for models that ignore the JSON request.
        if not (shape or color):
            shape = txt.lower()
            color = txt.lower()
        has_shape = any(k in shape for k in ("圆", "circle", "circular"))
        has_color = any(k in color for k in ("红", "red", "crimson", "scarlet"))
        if has_shape and has_color:
            log.info("vision probe ok: model=%s reply=%s", model, txt[:60])
            return {"has_vision": True, "reply": txt}
        log.warning("vision probe failed: model=%s reply=%s", model, txt[:80])
        return {"has_vision": False,
                "reason": f"模型未能正确描述测试图：{txt[:60]}"}
    except Exception as e:
        log.warning("vision probe error: model=%s err=%s", model, e)
        return {"has_vision": False, "reason": f"API_ERROR: {e}"}
