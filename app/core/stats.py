# -*- coding: utf-8 -*-
"""Inter-rater reliability: ICC(2,1) across videos and raters."""
import json

import numpy as np

from .storage import get_conn


def compute_icc_matrix(dim_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, rater_id, scores FROM scores
                 WHERE method='subjective' AND is_valid=1""")
    rows = c.fetchall(); conn.close()
    data = {}
    raters = set()
    for vid, rater, sc_json in rows:
        sc = json.loads(sc_json)
        if dim_id in sc and sc[dim_id].get("value") is not None:
            data.setdefault(vid, {})[rater] = float(sc[dim_id]["value"])
            raters.add(rater)
    raters = sorted(raters)
    if len(raters) < 2:
        return None
    matrix = [data[vid] for vid in data if all(r in data[vid] for r in raters)]
    if len(matrix) < 2:
        return None
    M = np.array([[row[r] for r in raters] for row in matrix])
    n, k = M.shape
    grand = M.mean()
    col_means = M.mean(axis=0)
    row_means = M.mean(axis=1)
    BMS = k * np.sum((row_means - grand) ** 2) / (n - 1)
    WMS = np.sum((M - row_means[:, None] - col_means[None, :] + grand) ** 2) / (n * (k - 1))
    if BMS + (k - 1) * WMS == 0:
        return None
    icc = (BMS - WMS) / (BMS + (k - 1) * WMS)
    return round(float(icc), 3)


def compute_krippendorff_alpha(dim_id):
    """Krippendorff's α (interval data) across videos (units) and raters.

    Uses the same source as compute_icc_matrix: method='subjective',
    is_valid=1. Returns None when there are fewer than 2 rated units or a
    unit with <2 raters.
    """
    conn = get_conn(); c = conn.cursor()
    c.execute("""SELECT video_id, rater_id, scores FROM scores
                 WHERE method='subjective' AND is_valid=1""")
    rows = c.fetchall(); conn.close()
    units = {}
    for vid, rater, sc_json in rows:
        sc = json.loads(sc_json)
        if dim_id in sc and isinstance(sc[dim_id], dict) and sc[dim_id].get("value") is not None:
            units.setdefault(vid, {})[rater] = float(sc[dim_id]["value"])
    units = {v: d for v, d in units.items() if len(d) >= 2}
    if len(units) < 2:
        return None
    all_vals = [val for d in units.values() for val in d.values()]
    n = len(all_vals)
    do = 0.0
    de = 0.0
    for d in units.values():
        vals = list(d.values())
        nu = len(vals)
        s_obs = 0.0
        for i in range(nu):
            for j in range(i + 1, nu):
                s_obs += (vals[i] - vals[j]) ** 2
        do += s_obs
        mu = sum(vals) / nu
        s_var = sum((v - mu) ** 2 for v in vals)
        de += (nu / (nu - 1)) * s_var
    if n - 1 == 0:
        return None
    do /= (n - 1)
    de /= (n - 1)
    if de == 0:
        return None
    alpha = 1 - do / de
    return round(float(alpha), 3)
