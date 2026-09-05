"""تست‌های ماژول تشخیص خودکار مدل (diagnostics.pick_model) — خالص و بدون شبکه."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from diagnostics import matches_family_of, pick_model  # noqa: E402

# مدل‌های واقعی کاربر (ویندوز)
USER_MODELS = [
    "huihui_ai/Qwen3.8-abliterated:27b",
    "minimax-m3:cloud",
    "hf.co/unsloth/Qwen3.8-27B-GGUF:Q8_0",
    "hf.co/MaralGPT/MaralGPT-Mythos-9B-2606-GGUF:Q8_0",
    "qwen-coder:latest",
    "huihui_ai/qwen3-coder-abliterated:30b-a3b",
    "hf.co/saeedalone/alduin-4b-it-base-GGUF:latest",
]


def test_exact_match_returns_desired():
    model, reason = pick_model(USER_MODELS, "qwen-coder:latest")
    assert model == "qwen-coder:latest"
    assert reason is None


def test_fuzzy_prefix_match_fixes_wrong_tag():
    """سناریوی واقعی باگ: تگ پیش‌فرض q4_K_M بود ولی تگ نصب‌شده 30b-a3b است."""
    model, reason = pick_model(
        USER_MODELS, "huihui_ai/qwen3-coder-abliterated:30b-a3b-instruct-q4_K_M"
    )
    assert model == "huihui_ai/qwen3-coder-abliterated:30b-a3b"
    assert reason and "نصب نیست" in reason


def test_family_match_same_base():
    """هم‌خانواده (قبل از ":") هم باید تطبیق شود."""
    model, _ = pick_model(["qwen3:4b", "qwen-coder:latest"], "qwen3:8b")
    assert model == "qwen3:4b"


def test_preference_order_picks_qwen3_coder():
    model, _ = pick_model(USER_MODELS, None)
    assert model == "huihui_ai/qwen3-coder-abliterated:30b-a3b"


def test_tool_capable_model_wins_over_tool_less():
    """اگر بدانیم alduin ابزار ندارد و qwen3 دارد، باید qwen3 انتخاب شود."""
    tools = {name: ("qwen3" in name or "coder" in name) for name in USER_MODELS}
    model, reason = pick_model(USER_MODELS, None, tool_support=tools)
    assert "qwen3" in model or "coder" in model


def test_tool_less_fallback_when_only_option():
    """وقتی هیچ مدل ابزارداری نیست، اولین مدل برگردانده می‌شود (نه crash)."""
    tools = {name: False for name in USER_MODELS}
    model, _ = pick_model(USER_MODELS, None, tool_support=tools)
    assert model in USER_MODELS


def test_empty_installed_returns_desired():
    model, reason = pick_model([], "anything:1b")
    assert model == "anything:1b"
    assert reason is None


def test_matches_family_of_helper():
    assert matches_family_of("a/b:1", "a/b:2")
    assert matches_family_of("qwen3:4b", "qwen3:4b-instruct")
    assert not matches_family_of("qwen3:4b", "llama3:8b")
