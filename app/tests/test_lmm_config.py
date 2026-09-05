# -*- coding: utf-8 -*-
"""API Key 脱敏展示与 LMM 配置持久化。"""
import json

from core import storage

LONG_KEY = "sk-" + "a" * 32          # 35 位，模拟真实 DeepSeek Key 长度
BASE = "https://api.example.com/v1"


def _persisted():
    with open(storage.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_mask_keeps_head_and_tail_ten_chars():
    m = storage.mask_api_key(LONG_KEY)
    assert m.startswith(LONG_KEY[:10])
    assert m.endswith(LONG_KEY[-10:])
    assert m.count("*") == len(LONG_KEY) - 20


def test_mask_never_leaks_full_key():
    m = storage.mask_api_key(LONG_KEY)
    assert LONG_KEY not in m
    assert m != LONG_KEY


def test_mask_short_key_still_hidden():
    m = storage.mask_api_key("sk-abc123")
    assert "*" in m
    assert m != "sk-abc123"


def test_mask_empty_key():
    assert storage.mask_api_key("") == ""


def test_save_persists_base_url_model_and_key():
    storage.save_lmm_config(BASE, "vision-model", LONG_KEY)
    cfg = _persisted()
    assert cfg["lmm"]["base_url"] == BASE
    assert cfg["lmm"]["model"] == "vision-model"
    assert cfg["lmm"]["api_key"] == LONG_KEY


def test_save_ignores_masked_key():
    """回显的脱敏串被当作 Key 提交时，必须保留原 Key 而不是写入星号。"""
    storage.save_lmm_config(BASE, "m1", LONG_KEY)
    storage.save_lmm_config(BASE, "m2", storage.mask_api_key(LONG_KEY))
    cfg = _persisted()
    assert cfg["lmm"]["api_key"] == LONG_KEY
    assert cfg["lmm"]["model"] == "m2"


def test_save_with_blank_key_keeps_previous():
    storage.save_lmm_config(BASE, "m1", LONG_KEY)
    storage.save_lmm_config(BASE, "m2", "")
    assert _persisted()["lmm"]["api_key"] == LONG_KEY


def test_masked_view_contains_no_plaintext():
    storage.save_lmm_config(BASE, "m1", LONG_KEY)
    view = storage.load_lmm_config_masked()
    assert view["has_key"] is True
    assert LONG_KEY not in json.dumps(view, ensure_ascii=False)
    assert view["api_key_masked"].startswith(LONG_KEY[:10])
    assert view["base_url"] == BASE and view["model"] == "m1"


def test_masked_view_when_no_key():
    storage.save_lmm_config(BASE, "m1", "")
    view = storage.load_lmm_config_masked()
    assert view["has_key"] is False
    assert view["api_key_masked"] == ""
