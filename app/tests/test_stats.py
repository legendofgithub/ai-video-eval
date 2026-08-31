# -*- coding: utf-8 -*-
"""Statistical reliability formula regression tests."""
import json
import uuid
from datetime import datetime

from core import storage
from core.stats import compute_icc_matrix, compute_krippendorff_alpha


def _add_subjective(video_id, rater_id, value, dim_id="D01"):
    conn = storage.get_conn()
    conn.execute(
        "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            uuid.uuid4().hex[:10], "task_test", video_id, storage.DEFAULT_SPEC_ID,
            rater_id, "user", "subjective", None,
            json.dumps({dim_id: {"value": value, "confidence": None, "note": ""}}),
            None, 1, datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def test_krippendorff_matches_interval_formula():
    for vid, r1, r2 in (("v1", 1.0, 2.0), ("v2", 3.0, 4.0)):
        _add_subjective(vid, "r1", r1)
        _add_subjective(vid, "r2", r2)
    assert compute_krippendorff_alpha("D01") == 0.7


def test_krippendorff_perfect_between_units_is_one():
    for vid, value in (("v1", 1.0), ("v2", 2.0), ("v3", 3.0)):
        for rater in ("r1", "r2", "r3"):
            _add_subjective(vid, rater, value)
    assert compute_krippendorff_alpha("D01") == 1.0


def test_icc_uses_absolute_agreement_denominator():
    for vid, r1, r2 in (("v1", 1.0, 2.0), ("v2", 3.0, 4.0), ("v3", 5.0, 6.0)):
        _add_subjective(vid, "r1", r1)
        _add_subjective(vid, "r2", r2)
    assert compute_icc_matrix("D01") == 0.889
