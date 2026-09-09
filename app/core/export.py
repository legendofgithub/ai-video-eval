# -*- coding: utf-8 -*-
"""VBench-compatible export and human-score aggregation."""
import json
import os

import numpy as np

from . import storage
from .dimensions import DIM_IDS, DEFAULT_SPEC_ID
from .storage import get_conn


def _human_score_rows():
    """Per-video effective human scores: expert arbitration overrides
    subjective means. Returns list of (video_id, model_tag, scores_dict)."""
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT s.video_id, v.model_tag, s.method, s.scores, s.is_valid
                 FROM scores s JOIN videos v ON v.video_id=s.video_id
                 ORDER BY s.created_at, s.score_id""")
    rows = c.fetchall(); conn.close()
    by_vid = {}
    for vid, tag, method, sc_json, is_valid in rows:
        sc = json.loads(sc_json)
        d = by_vid.setdefault(vid, {"model_tag": tag, "expert": {}, "sub": []})
        if method == "expert_arbitration" and is_valid == 1:
            for dim, raw in sc.items():
                if _dim_value({dim: raw}, dim) is not None:
                    d["expert"][dim] = raw
        elif method == "subjective" and is_valid == 1:
            d["sub"].append(sc)
    out = []
    for vid, d in by_vid.items():
        merged = {}
        for sc in d["sub"]:
            for dim, v in sc.items():
                if isinstance(v, dict) and v.get("value") is not None:
                    merged.setdefault(dim, []).append(v["value"])
        effective = {dim: round(float(np.mean(vals)), 2)
                     for dim, vals in merged.items()}
        effective.update(d["expert"])
        if effective:
            out.append((vid, d["model_tag"], effective))
    return out


def _dim_value(sc, dim):
    """Parse one dimension value (supports {value:..} and bare float)."""
    v = sc.get(dim)
    if isinstance(v, dict):
        return v.get("value")
    return v


def export_vbench():
    data = _human_score_rows()
    model_dims = {}
    for vid, tag, sc in data:
        if not tag:
            continue
        for d in DIM_IDS:
            val = _dim_value(sc, d)
            if val is not None:
                model_dims.setdefault(tag, {}).setdefault(d, []).append(float(val))
    leaderboard = []
    for tag, dd in model_dims.items():
        mean_scores = {d: round(float(np.mean(dd[d])), 2) if d in dd else None for d in DIM_IDS}

        def _lm(keys):
            lst = [mean_scores[x] for x in keys if mean_scores[x] is not None]
            return float(np.mean(lst)) if lst else 0.0

        layer_means = {
            "technical": _lm(("D01", "D02", "D03", "D04")),
            "semantic": _lm(("D05", "D06", "D07")),
            "world_model": _lm(("D08", "D09", "D10")),
        }
        leaderboard.append({"model_tag": tag, "mean_scores": mean_scores,
                            "layer_means": {k: round(float(v), 2) for k, v in layer_means.items()}})
    out = {"export_version": "vbench_compat_1.0", "spec_id": DEFAULT_SPEC_ID,
           "mos_scale": 10, "leaderboard": leaderboard}
    out_path = os.path.join(storage.DATA, "vbench_export.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out_path


def _layer_mean(scores: dict, keys) -> float | None:
    lst = [scores[k] for k in keys if k in scores and scores[k] is not None]
    return round(float(np.mean(lst)), 2) if lst else None


def _append_score(target: dict, dim: str, val) -> None:
    if val is None:
        return
    try:
        fv = float(val)
    except (TypeError, ValueError):
        return
    if 0 <= fv <= 10:
        target.setdefault(dim, []).append(fv)


LAYER_GROUPS = {
    "technical": ("D01", "D02", "D03", "D04"),
    "semantic": ("D05", "D06", "D07"),
    "world_model": ("D08", "D09", "D10"),
}


def dashboard_data() -> dict:
    """Aggregate all scores (objective + subjective + expert arbitration) into
    per-video / per-model leaderboards, a MOS histogram and a world-model
    sub-board. Zero external dependencies; pure SQLite + numpy."""
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT s.video_id, v.filename, v.model_tag, s.method, s.scores,
                        s.is_valid
                 FROM scores s JOIN videos v ON v.video_id = s.video_id
                 ORDER BY s.created_at, s.score_id""")
    rows = c.fetchall(); conn.close()

    by_vid: dict = {}
    mos_scores: list = []
    for vid, fn, tag, method, sc_json, is_valid in rows:
        sc = json.loads(sc_json)
        d = by_vid.setdefault(vid, {"filename": fn, "model_tag": tag or "",
                                    "vals": {}, "sub": {}, "expert": {},
                                    "human": {}})
        if method == "objective":
            for dim in sc:
                val = _dim_value(sc, dim)
                _append_score(d["vals"], dim, val)
        elif method == "subjective" and is_valid == 1:
            for dim in sc:
                _append_score(d["sub"], dim, _dim_value(sc, dim))
        elif method == "expert_arbitration" and is_valid == 1:
            for dim, raw in sc.items():
                val = _dim_value({dim: raw}, dim)
                if val is not None:
                    d["expert"][dim] = val

    videos = []
    all_scores: list = []
    for vid, d in by_vid.items():
        for dim, vals in d["sub"].items():
            if vals:
                d["human"][dim] = round(float(np.mean(vals)), 2)
        for dim, val in d["expert"].items():
            if val is not None:
                d["human"][dim] = val
        objective_mean_scores = {
            dim: round(float(np.mean(vals)), 2)
            for dim, vals in d["vals"].items() if vals
        }
        human_mean_scores = {
            dim: round(float(np.mean(vals)), 2)
            for dim, vals in d["human"].items() if vals
        }
        for dim, val in d["human"].items():
            d["vals"].setdefault(dim, []).append(val)
            mos_scores.append(val)
        mean_scores = {}
        for dim in DIM_IDS:
            if dim in d["vals"]:
                mean_scores[dim] = round(float(np.mean(d["vals"][dim])), 2)
                all_scores.extend(d["vals"][dim])
        layer_means = {k: _layer_mean(mean_scores, v) for k, v in LAYER_GROUPS.items()}
        overall = _layer_mean(mean_scores, DIM_IDS)
        videos.append({
            "video_id": vid,
            "filename": d["filename"],
            "model_tag": d["model_tag"] or "未标注",
            "mean_scores": mean_scores,
            "objective_mean_scores": objective_mean_scores,
            "human_mean_scores": human_mean_scores,
            "layer_means": layer_means,
            "overall": overall,
            "n_ratings": sum(len(x) for x in d["vals"].values()),
        })

    by_model: dict = {}
    for v in videos:
        m = by_model.setdefault(v["model_tag"], {"mean_scores": {}, "count": 0})
        m["count"] += 1
        for dim, val in v["mean_scores"].items():
            m["mean_scores"].setdefault(dim, []).append(val)
    models = []
    for tag, m in by_model.items():
        ms = {dim: round(float(np.mean(m["mean_scores"][dim])), 2)
              if dim in m["mean_scores"] else None for dim in DIM_IDS}
        models.append({
            "model_tag": tag,
            "n_videos": m["count"],
            "mean_scores": ms,
            "layer_means": {k: _layer_mean(ms, v) for k, v in LAYER_GROUPS.items()},
            "overall": _layer_mean(ms, DIM_IDS),
        })

    if mos_scores:
        arr = np.array(mos_scores)
        counts, edges = np.histogram(arr, bins=10, range=(0, 10))
        mos_hist = [{"bin": f"{int(edges[i])}-{int(edges[i + 1])}",
                     "count": int(counts[i])} for i in range(len(counts))]
    else:
        mos_hist = [{"bin": f"{i}-{i + 1}", "count": 0} for i in range(10)]

    world_model = [{
        "video_id": v["video_id"],
        "filename": v["filename"],
        "D08": v["mean_scores"].get("D08"),
        "D09": v["mean_scores"].get("D09"),
        "D10": v["mean_scores"].get("D10"),
        "world_mean": v["layer_means"]["world_model"],
    } for v in videos]

    summary = {
        "n_videos": len(videos),
        "n_ratings": int(sum(len(lst) for d in by_vid.values() for lst in d["vals"].values())),
        "overall_mean": round(float(np.mean(all_scores)), 2) if all_scores else None,
    }
    return {"videos": videos, "models": models, "mos_hist": mos_hist,
            "world_model": world_model, "summary": summary}
