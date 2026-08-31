# -*- coding: utf-8 -*-
"""Inter-rater reliability: ICC(2,1) and Krippendorff's alpha."""
from collections import Counter

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
    CMS = n * np.sum((col_means - grand) ** 2) / (k - 1)
    denominator = BMS + (k - 1) * WMS + (k / n) * (CMS - WMS)
    if denominator == 0:
        return None
    icc = (BMS - WMS) / denominator
    return round(float(icc), 3)


def compute_krippendorff_alpha(dim_id):
    """Krippendorff's α (interval data) across videos (units) and raters.

    Uses the same source as compute_icc_matrix: method='subjective',
    is_valid=1. Returns None when there are fewer than 2 rated units, a
    unit has <2 raters, or agreement is undefined because all values match.
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
    observed: dict[float, dict[float, float]] = {}
    value_counts: Counter[float] = Counter()
    for ratings in units.values():
        counts = Counter(ratings.values())
        pairable = sum(counts.values())
        values = sorted(counts)
        for i, left in enumerate(values):
            value_counts[left] += counts[left]
            row = observed.setdefault(left, {})
            row[left] = row.get(left, 0.0) + counts[left] * (counts[left] - 1) / (pairable - 1)
            for right in values[i + 1:]:
                pair = counts[left] * counts[right] / (pairable - 1)
                row[right] = row.get(right, 0.0) + pair
                reverse = observed.setdefault(right, {})
                reverse[left] = reverse.get(left, 0.0) + pair

    values = sorted(value_counts)
    if len(values) < 2:
        return None
    total_values = sum(value_counts.values())
    observed_distance = 0.0
    expected_distance = 0.0
    for i, left in enumerate(values):
        for right in values[i:]:
            distance = (left - right) ** 2
            observed_distance += distance * observed.get(left, {}).get(right, 0.0)
            expected_count = (
                value_counts[left] * value_counts[right]
                - (right == left) * value_counts[left]
            ) / (total_values - 1)
            expected_distance += distance * expected_count
    if expected_distance == 0:
        return None
    alpha = 1 - observed_distance / expected_distance
    return round(float(alpha), 3)
