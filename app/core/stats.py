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
