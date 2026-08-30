# -*- coding: utf-8 -*-
"""VBench-compatible export and human-score aggregation."""
import json
import os

import numpy as np

from .dimensions import DIM_IDS, DEFAULT_SPEC_ID
from .storage import BASE, get_conn


def _human_score_rows():
    """Per-video effective human scores: expert arbitration overrides
    subjective means. Returns list of (video_id, model_tag, scores_dict)."""
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT s.video_id, v.model_tag, s.method, s.scores, s.is_valid
                 FROM scores s JOIN videos v ON v.video_id=s.video_id""")
    rows = c.fetchall(); conn.close()
    by_vid = {}
    for vid, tag, method, sc_json, is_valid in rows:
        sc = json.loads(sc_json)
        d = by_vid.setdefault(vid, {"model_tag": tag, "expert": None, "sub": []})
        if method == "expert_arbitration":
            d["expert"] = sc
        elif method == "subjective" and is_valid == 1:
            d["sub"].append(sc)
    out = []
    for vid, d in by_vid.items():
        if d["expert"] is not None:
            out.append((vid, d["model_tag"], d["expert"]))
        elif d["sub"]:
            merged = {}
            for sc in d["sub"]:
                for dim, v in sc.items():
                    if isinstance(v, dict) and v.get("value") is not None:
                        merged.setdefault(dim, []).append(v["value"])
            merged = {dim: round(float(np.mean(vals)), 2) for dim, vals in merged.items()}
            out.append((vid, d["model_tag"], merged))
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
    out_path = os.path.join(BASE, "vbench_export.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out_path
