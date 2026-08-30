# -*- coding: utf-8 -*-
"""AI 生成视频质量评测工具 — Gradio UI 层 (v0.4)

核心逻辑（存储/媒体/LMM/本地信号/统计/导出）统一在 core/ 包中维护，
本文件只负责 Gradio 界面与 Plotly 可视化，不再自带业务副本。
"""
import datetime
import json
import uuid

import gradio as gr
import plotly.graph_objects as go

from core import (
    DIMENSIONS, DIM_IDS, DIM_NAME, DEFAULT_SPEC_ID, TEMPORAL_SIGNAL_DIMS,
    BASE, DATA, VIDEOS_DIR, FRAMES_DIR, DB, CONFIG_PATH,
    get_conn, init_db, load_config, save_config,
    add_video as _core_add_video, delete_video, get_video_path, list_videos,
    save_subjective, insert_objective_score,
    md5_file, video_meta, validate_video, sample_frames, frame_to_b64,
    build_dim_prompt, score_one_dim, probe_vision,
    signal_metrics, auto_evaluate,
    compute_icc_matrix, _human_score_rows, _dim_value, export_vbench,
)


# ---------------- UI / 兼容适配层 ----------------
def add_video(file_obj, url, prompt_text, model_tag):
    """Gradio 兼容签名：file_obj 由上传组件提供，返回 (video_id, 消息)。"""
    if file_obj is None:
        return None, "未提供视频文件"
    src = file_obj.name if hasattr(file_obj, "name") else file_obj
    try:
        r = _core_add_video(src, prompt_text or "", model_tag or "")
    except ValueError as e:
        return None, f"入库失败: {e}"
    if r.get("duplicate"):
        return r["video_id"], f"视频已存在，复用 video_id={r['video_id']}"
    return r["video_id"], (f"已入库 video_id={r['video_id']} "
                           f"({r['resolution']}, {r['duration_sec']}s)")


def video_choices():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT video_id, filename, model_tag FROM videos ORDER BY created_at DESC")
    rows = c.fetchall(); conn.close()
    return [(f"{r[0]} | {r[1]} | {r[2] or '-'}", r[0]) for r in rows]


# ---------------- 可视化 ----------------
def radar_fig(video_id):
    """雷达图：机器客观分(LMM+本地信号) 与 人工/专家分 两条独立 trace，不混算。"""
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT method, scores FROM scores WHERE video_id=?", (video_id,))
    rows = c.fetchall(); conn.close()
    obj = {d: [] for d in DIM_IDS}
    for method, sc_json in rows:
        if method != "objective":
            continue
        sc = json.loads(sc_json)
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                obj[d].append(val)
    human_map = {vid: sc for vid, tag, sc in _human_score_rows()}
    hsc = human_map.get(video_id, {})
    obj_vals = [round(float(sum(obj[d]) / len(obj[d])), 2) if obj[d] else 0 for d in DIM_IDS]
    human_vals = [_dim_value(hsc, d) if _dim_value(hsc, d) is not None else 0 for d in DIM_IDS]
    fig = go.Figure()
    if any(obj_vals):
        fig.add_trace(go.Scatterpolar(r=obj_vals + [obj_vals[0]], theta=DIM_IDS + [DIM_IDS[0]],
                                      fill="toself", name="机器客观分(LMM+本地信号)"))
    if any(human_vals):
        fig.add_trace(go.Scatterpolar(r=human_vals + [human_vals[0]], theta=DIM_IDS + [DIM_IDS[0]],
                                      fill="toself", name="人工/专家分(MOS)"))
    if not fig.data:
        fig.add_trace(go.Scatterpolar(r=[0] * 11, theta=DIM_IDS + [DIM_IDS[0]], name="暂无数据"))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 10])),
                      title=f"10 维雷达图 — {video_id}（客观 vs 人工，已区分）")
    return fig


def comparison_fig():
    """各模型按维度均值对比（人工/专家有效分，专家仲裁覆盖主观分）"""
    data = _human_score_rows()
    model_dims = {}
    for vid, tag, sc in data:
        if not tag:
            continue
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                model_dims.setdefault(tag, {}).setdefault(d, []).append(float(val))
    if not model_dims:
        return go.Figure()
    models = list(model_dims.keys())
    fig = go.Figure()
    for d in DIM_IDS:
        ys = [round(float(sum(model_dims[m][d]) / len(model_dims[m][d])), 2)
              if d in model_dims[m] else 0 for m in models]
        fig.add_trace(go.Bar(x=models, y=ys, name=DIM_NAME[d]))
    fig.update_layout(barmode="group", title="各模型按维度均值对比(人工/专家分)", yaxis_range=[0, 10])
    return fig


def icc_table():
    res = []
    for d in DIM_IDS:
        icc = compute_icc_matrix(d)
        res.append({"维度": f"{d} {DIM_NAME[d]}", "ICC(2,1)": icc if icc is not None else "样本不足",
                    "预警": "⚠️<0.6" if (icc is not None and icc < 0.6) else "OK"})
    return res


# =================== Gradio UI ===================
init_db()
with gr.Blocks(title="AI 视频质量评测工具") as app:
    gr.Markdown("# AI 生成视频质量评测工具 (v0.4)\n本地自用 · 10 维 · LMM 自动 + 人工 MOS + 专家仲裁 · core 单一核心")

    with gr.Tab("① 上传与任务"):
        with gr.Row():
            up_file = gr.Video(label="上传视频 (mp4/webm/mov)")
            with gr.Column():
                up_url = gr.Textbox(label="或填写视频 URL (公开直链)")
                up_prompt = gr.Textbox(label="生成提示 prompt (D07 必需)")
                up_model = gr.Textbox(label="生成模型/版本标识 (如 self_test_v2)")
                up_btn = gr.Button("入库")
                up_out = gr.Textbox(label="结果")
        up_btn.click(add_video, [up_file, up_url, up_prompt, up_model], up_out)

    with gr.Tab("② LMM 自动评测"):
        ae_vid = gr.Dropdown(label="选择视频", choices=video_choices())
        ae_dims = gr.CheckboxGroup(label="评测维度", choices=DIM_IDS, value=DIM_IDS)
        ae_btn = gr.Button("运行自动打分")
        ae_out = gr.JSON(label="客观分结果")
        def run_ae(vid, dims):
            if not vid:
                return {"error": "请先选择视频"}
            conn = get_conn(); c = conn.cursor()
            c.execute("SELECT prompt_text FROM videos WHERE video_id=?", (vid,))
            r = c.fetchone(); conn.close()
            lmm_cfg = load_config()["lmm"]
            res = auto_evaluate(vid, dims, lmm_cfg, r[0] if r else None)
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:10], "task_auto", vid, DEFAULT_SPEC_ID,
                       "lmm_" + lmm_cfg["model"], "lmm_auto", "objective",
                       lmm_cfg["model"], json.dumps(res, ensure_ascii=False), None, 1,
                       datetime.datetime.now().isoformat()))
            conn.commit(); conn.close()
            return res
        ae_btn.click(run_ae, [ae_vid, ae_dims], ae_out)
        gr.Markdown("说明：D03 时序闪烁、D04 运动平滑度 **自动走本地 CPU 信号指标（光流/帧差分，零成本、无需 API）**；"
                    "其余 8 维走 LMM 视觉模型（需在「⑥ 设置」填入视觉 API，如 DeepSeek-V4-vision / GPT-4o / Gemini / 本地 Ollama+DeepSeek-VL2）。"
                    "即使无 API Key，本地信号维度仍可正常出分。")

    with gr.Tab("③ 人工标注台"):
        an_vid = gr.Dropdown(label="选择视频", choices=video_choices())
        an_player = gr.Video(label="播放 (可慢放/逐帧)")
        an_vid.change(lambda v: get_video_path(v), an_vid, an_player)
        an_sliders = {}
        with gr.Row():
            for d in DIMENSIONS:
                an_sliders[d["dim_id"]] = gr.Slider(0, 10, step=0.5, label=f"{d['dim_id']} {d['name']}\n({d['layer']})")
        an_gate = gr.Radio(["technical", "physical", "semantic", "na"], label="低分归因门控 (技术失真/物理常识/语义不符/无)", value="na")
        an_rater = gr.Textbox(label="标注员 ID", value="u_001")
        an_note = gr.Textbox(label="备注 / 高层维违规note (类型@时间戳;置信度)")
        an_ab_choice = gr.Radio(["A", "B", "tie", ""], label="A-B 配对偏好 (可选)")
        an_ab_vs = gr.Dropdown(label="对比视频 (A-B)", choices=video_choices(), value=None)
        an_btn = gr.Button("提交评分")
        an_out = gr.Textbox(label="结果")
        def collect_and_save(vid, *vals):
            dims_vals = {DIM_IDS[i]: v for i, v in enumerate(vals[:-5])}
            gate = vals[-5]; rater = vals[-4]; note = vals[-3]; ab_c = vals[-2]; ab_vs = vals[-1]
            return save_subjective(vid, "user", rater, dims_vals, gate, note, ab_c, ab_vs)
        an_btn.click(collect_and_save,
                     [an_vid] + [an_sliders[d] for d in DIM_IDS] + [an_gate, an_rater, an_note, an_ab_choice, an_ab_vs],
                     an_out)

    with gr.Tab("④ 专家仲裁"):
        ex_vid = gr.Dropdown(label="选择争议视频", choices=video_choices())
        ex_player = gr.Video(label="播放")
        ex_vid.change(lambda v: get_video_path(v), ex_vid, ex_player)
        ex_sliders = {}
        with gr.Row():
            for d in DIMENSIONS:
                ex_sliders[d["dim_id"]] = gr.Slider(0, 10, step=0.5, label=f"{d['dim_id']} {d['name']}")
        ex_rater = gr.Textbox(label="专家 ID", value="exp_tony")
        ex_btn = gr.Button("提交仲裁 (覆盖)")
        ex_out = gr.Textbox(label="结果")
        def ex_save(vid, *vals):
            dims_vals = {DIM_IDS[i]: v for i, v in enumerate(vals[:-1])}
            return save_subjective(vid, "expert", vals[-1], dims_vals, "na", "", "", "")
        ex_btn.click(ex_save, [ex_vid] + [ex_sliders[d] for d in DIM_IDS] + [ex_rater], ex_out)

    with gr.Tab("⑤ 可视化看板"):
        vb_vid = gr.Dropdown(label="雷达图视频", choices=video_choices())
        vb_radar = gr.Plot()
        vb_vid.change(radar_fig, vb_vid, vb_radar)
        vb_bar = gr.Plot(label="模型对比柱状图")
        vb_bar_btn = gr.Button("生成模型对比")
        vb_bar_btn.click(comparison_fig, None, vb_bar)
        vb_icc = gr.DataFrame(icc_table(), label="ICC(2,1) 一致性 (主观有效分)")
        vb_icc_btn = gr.Button("刷新 ICC")
        vb_icc_btn.click(icc_table, None, vb_icc)
        vb_exp = gr.Button("导出 VBench 兼容 JSON")
        vb_exp_out = gr.Textbox(label="导出路径")
        vb_exp.click(export_vbench, None, vb_exp_out)

    with gr.Tab("⑥ 设置 (LMM API)"):
        st_provider = gr.Textbox(label="provider")
        st_base = gr.Textbox(label="base_url (OpenAI 兼容)")
        st_key = gr.Textbox(label="api_key", type="password")
        st_model = gr.Textbox(label="model (如 deepseek-vl2 / gpt-4o / gemini-2.0-flash)")
        st_nf = gr.Number(label="抽帧数", value=8)
        st_btn = gr.Button("保存设置")
        st_out = gr.Textbox(label="结果")
        def load_to_ui():
            c = load_config()["lmm"]
            return c["provider"], c["base_url"], c["api_key"], c["model"], c["n_frames"]
        def save_ui(p, b, k, m, n):
            cfg = load_config()
            cfg["lmm"] = {"provider": p, "base_url": b, "api_key": k, "model": m,
                          "n_frames": int(n), "temperature": 0.0, "samplings": 1}
            save_config(cfg)
            return "已保存"
        app.load(load_to_ui, None, [st_provider, st_base, st_key, st_model, st_nf])
        st_btn.click(save_ui, [st_provider, st_base, st_key, st_model, st_nf], st_out)

if __name__ == "__main__":
    app.launch()
