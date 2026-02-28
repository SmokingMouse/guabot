from __future__ import annotations

import pytest
from typing import Any, Dict, List, Literal

from guabot.context_compression import (
    CompressionConfig,
    ContextCompressor,
)

# 简化的 MessageParam 类型
MessageParam = Dict[str, Any]


def test_should_compress_when_above_threshold():
    """测试当使用率超过阈值时应该触发压缩"""
    config = CompressionConfig(enabled=True, trigger_threshold=0.8)
    compressor = ContextCompressor(config)

    # 使用率 85% > 80%
    assert compressor.should_compress(current_tokens=8500, context_limit=10000) is True

    # 使用率 75% < 80%
    assert compressor.should_compress(current_tokens=7500, context_limit=10000) is False


def test_should_not_compress_when_disabled():
    """测试禁用压缩时不应触发"""
    config = CompressionConfig(enabled=False)
    compressor = ContextCompressor(config)

    assert compressor.should_compress(current_tokens=9500, context_limit=10000) is False


def test_compress_messages_basic():
    """测试基本的消息压缩功能"""
    config = CompressionConfig(
        enabled=True,
        trigger_threshold=0.8,
        target_threshold=0.6,
        keep_recent_turns=2,  # 保留最近 2 轮
    )
    compressor = ContextCompressor(config)

    # 构造 6 轮对话 (12 条消息)
    messages: list[MessageParam] = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]

    for i in range(6):
        messages.append({"role": "user", "content": f"User message {i+1}" * 20})
        messages.append({"role": "assistant", "content": f"Assistant response {i+1}" * 20})

    # 当前 tokens 假设为 8500, limit 10000
    result = compressor.compress_messages(
        messages=messages,
        current_tokens=8500,
        context_limit=10000,
        llm_client=None
    )

    # 应该压缩了一些消息
    assert result.compressed_count > 0
    assert len(result.compressed_messages) < len(messages)

    # system 消息应该保留
    assert result.compressed_messages[0]["role"] == "system"

    # 最近的消息应该保留
    assert any("User message 6" in str(m.get("content", "")) for m in result.compressed_messages)
    assert any("Assistant response 6" in str(m.get("content", "")) for m in result.compressed_messages)


def test_compress_messages_keeps_recent():
    """测试压缩时保留最近的消息"""
    config = CompressionConfig(keep_recent_turns=3)
    compressor = ContextCompressor(config)

    messages: list[MessageParam] = []
    for i in range(10):
        messages.append({"role": "user", "content": f"Turn {i+1}"})
        messages.append({"role": "assistant", "content": f"Response {i+1}"})

    result = compressor.compress_messages(
        messages=messages,
        current_tokens=8000,
        context_limit=10000,
        llm_client=None
    )

    # 最近 3 轮 (6 条消息) 应该保留
    compressed_content = str(result.compressed_messages)
    assert "Turn 10" in compressed_content
    assert "Turn 9" in compressed_content
    assert "Turn 8" in compressed_content


def test_compress_messages_no_compression_needed():
    """测试当没有可压缩消息时的行为"""
    config = CompressionConfig(keep_recent_turns=10)
    compressor = ContextCompressor(config)

    # 只有 3 轮对话,少于 keep_recent_turns
    messages: list[MessageParam] = []
    for i in range(3):
        messages.append({"role": "user", "content": f"Turn {i+1}"})
        messages.append({"role": "assistant", "content": f"Response {i+1}"})

    result = compressor.compress_messages(
        messages=messages,
        current_tokens=5000,
        context_limit=10000,
        llm_client=None
    )

    # 没有压缩
    assert result.compressed_count == 0
    assert len(result.compressed_messages) == len(messages)


def test_estimate_tokens():
    """测试 token 估算"""
    config = CompressionConfig()
    compressor = ContextCompressor(config)

    messages: list[MessageParam] = [
        {"role": "user", "content": "a" * 100},  # ~25 tokens
        {"role": "assistant", "content": "b" * 200},  # ~50 tokens
    ]

    estimated = compressor._estimate_tokens(messages)
    assert estimated > 0
    assert estimated < 100  # 应该在合理范围内


def test_compression_result_structure():
    """测试压缩结果的结构"""
    config = CompressionConfig(keep_recent_turns=1)
    compressor = ContextCompressor(config)

    messages: list[MessageParam] = []
    for i in range(5):
        messages.append({"role": "user", "content": f"Turn {i+1}"})
        messages.append({"role": "assistant", "content": f"Response {i+1}"})

    result = compressor.compress_messages(
        messages=messages,
        current_tokens=8000,
        context_limit=10000,
        llm_client=None
    )

    # 检查结果结构
    assert hasattr(result, "compressed_messages")
    assert hasattr(result, "compressed_count")
    assert hasattr(result, "original_token_count")
    assert hasattr(result, "compressed_token_count")
    assert hasattr(result, "compression_time")

    assert result.original_token_count == 8000
    assert result.compression_time >= 0
