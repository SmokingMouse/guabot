from __future__ import annotations

import asyncio
import pytest
import time

from guabot.skill_timeout import (
    TimeoutConfig,
    TimeoutManager,
    execute_with_timeout_sync,
)


def test_execute_with_timeout_success():
    """测试正常执行不超时"""
    config = TimeoutConfig(enabled=True, default_timeout=5.0)
    manager = TimeoutManager(config)

    def quick_func():
        return "success"

    result = execute_with_timeout_sync(quick_func, manager)

    assert result.success is True
    assert result.result == "success"
    assert result.timed_out is False
    assert result.execution_time < 1.0


def test_execute_with_timeout_timeout():
    """测试超时情况"""
    config = TimeoutConfig(enabled=True, default_timeout=0.5)
    manager = TimeoutManager(config)

    def slow_func():
        time.sleep(2.0)
        return "should not reach here"

    result = execute_with_timeout_sync(slow_func, manager, timeout=0.5)

    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in result.error.lower()
    assert result.execution_time >= 0.5


def test_execute_with_timeout_custom_timeout():
    """测试自定义超时时间"""
    config = TimeoutConfig(enabled=True, default_timeout=10.0)
    manager = TimeoutManager(config)

    def medium_func():
        time.sleep(0.3)
        return "done"

    # 使用自定义超时 1 秒 (大于 0.3 秒)
    result = execute_with_timeout_sync(medium_func, manager, timeout=1.0)

    assert result.success is True
    assert result.result == "done"
    assert result.timeout_threshold == 1.0


def test_execute_with_timeout_disabled():
    """测试禁用超时功能"""
    config = TimeoutConfig(enabled=False)
    manager = TimeoutManager(config)

    def slow_func():
        time.sleep(0.2)
        return "completed"

    result = execute_with_timeout_sync(slow_func, manager, timeout=0.1)

    # 即使设置了 0.1 秒超时,但功能禁用,所以应该成功
    assert result.success is True
    assert result.result == "completed"


def test_execute_with_timeout_exception():
    """测试函数抛出异常"""
    config = TimeoutConfig(enabled=True, default_timeout=5.0)
    manager = TimeoutManager(config)

    def error_func():
        raise ValueError("test error")

    result = execute_with_timeout_sync(error_func, manager)

    assert result.success is False
    assert result.timed_out is False
    assert "ValueError" in result.error
    assert "test error" in result.error


def test_timeout_result_structure():
    """测试超时结果的结构"""
    config = TimeoutConfig(enabled=True, default_timeout=1.0)
    manager = TimeoutManager(config)

    def quick_func():
        return 42

    result = execute_with_timeout_sync(quick_func, manager)

    # 检查结果结构
    assert hasattr(result, "success")
    assert hasattr(result, "result")
    assert hasattr(result, "error")
    assert hasattr(result, "timed_out")
    assert hasattr(result, "execution_time")
    assert hasattr(result, "timeout_threshold")


@pytest.mark.asyncio
async def test_execute_with_timeout_async():
    """测试异步函数的超时"""
    config = TimeoutConfig(enabled=True, default_timeout=1.0)
    manager = TimeoutManager(config)

    async def async_quick_func():
        await asyncio.sleep(0.1)
        return "async success"

    result = await manager.execute_with_timeout(async_quick_func)

    assert result.success is True
    assert result.result == "async success"
    assert result.execution_time >= 0.1


@pytest.mark.asyncio
async def test_execute_with_timeout_async_timeout():
    """测试异步函数超时"""
    config = TimeoutConfig(enabled=True, default_timeout=0.5)
    manager = TimeoutManager(config)

    async def async_slow_func():
        await asyncio.sleep(2.0)
        return "should not reach"

    result = await manager.execute_with_timeout(async_slow_func, timeout=0.5)

    assert result.success is False
    assert result.timed_out is True


def test_default_timeout_used():
    """测试使用默认超时时间"""
    config = TimeoutConfig(enabled=True, default_timeout=2.0)
    manager = TimeoutManager(config)

    def quick_func():
        return "ok"

    result = execute_with_timeout_sync(quick_func, manager)

    assert result.success is True
    # 应该使用默认的 2.0 秒超时
    assert result.timeout_threshold == 2.0


def test_execution_time_recorded():
    """测试执行时间被正确记录"""
    config = TimeoutConfig(enabled=True, default_timeout=5.0)
    manager = TimeoutManager(config)

    def timed_func():
        time.sleep(0.2)
        return "done"

    result = execute_with_timeout_sync(timed_func, manager)

    assert result.success is True
    # 执行时间应该接近 0.2 秒
    assert 0.15 < result.execution_time < 0.3
