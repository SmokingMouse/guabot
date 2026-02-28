from __future__ import annotations

import asyncio
import pytest
import time

from guabot.tool_retry import (
    RetryConfig,
    RetryStrategy,
    execute_with_retry_sync,
)


class NetworkError(Exception):
    """模拟网络错误"""
    pass


class AuthenticationError(Exception):
    """模拟认证错误"""
    pass


class TimeoutError(Exception):
    """模拟超时错误"""
    pass


def test_should_retry_for_retryable_errors():
    """测试可重试错误应该重试"""
    config = RetryConfig(
        enabled=True,
        default_max_retries=3,
        retryable_errors=["NetworkError", "TimeoutError"]
    )
    strategy = RetryStrategy(config)

    # NetworkError 应该重试
    assert strategy.should_retry(NetworkError("test"), attempt=1, elapsed_time=0) is True

    # TimeoutError 应该重试
    assert strategy.should_retry(TimeoutError("test"), attempt=1, elapsed_time=0) is True


def test_should_not_retry_for_non_retryable_errors():
    """测试不可重试错误不应该重试"""
    config = RetryConfig(
        enabled=True,
        non_retryable_errors=["AuthenticationError"]
    )
    strategy = RetryStrategy(config)

    # AuthenticationError 不应该重试
    assert strategy.should_retry(AuthenticationError("test"), attempt=1, elapsed_time=0) is False


def test_should_not_retry_when_max_retries_exceeded():
    """测试超过最大重试次数时不应该重试"""
    config = RetryConfig(default_max_retries=3)
    strategy = RetryStrategy(config)

    # attempt 3 < max 3, 应该重试
    assert strategy.should_retry(NetworkError("test"), attempt=3, elapsed_time=0) is False

    # attempt 4 > max 3, 不应该重试
    assert strategy.should_retry(NetworkError("test"), attempt=4, elapsed_time=0) is False


def test_should_not_retry_when_time_exceeded():
    """测试超过总时间限制时不应该重试"""
    config = RetryConfig(max_total_retry_time=10.0)
    strategy = RetryStrategy(config)

    # 9 秒 < 10 秒, 应该重试
    assert strategy.should_retry(NetworkError("test"), attempt=1, elapsed_time=9.0) is True

    # 11 秒 > 10 秒, 不应该重试
    assert strategy.should_retry(NetworkError("test"), attempt=1, elapsed_time=11.0) is False


def test_calculate_backoff_exponential():
    """测试指数退避计算"""
    config = RetryConfig(default_backoff_base=1.0)
    strategy = RetryStrategy(config)

    # attempt 1: 1.0 * 2^0 = 1.0
    assert strategy.calculate_backoff(1) == 1.0

    # attempt 2: 1.0 * 2^1 = 2.0
    assert strategy.calculate_backoff(2) == 2.0

    # attempt 3: 1.0 * 2^2 = 4.0
    assert strategy.calculate_backoff(3) == 4.0

    # attempt 4: 1.0 * 2^3 = 8.0
    assert strategy.calculate_backoff(4) == 8.0


def test_calculate_backoff_custom_base():
    """测试自定义退避基数"""
    config = RetryConfig(default_backoff_base=2.0)
    strategy = RetryStrategy(config)

    # attempt 1: 2.0 * 2^0 = 2.0
    assert strategy.calculate_backoff(1) == 2.0

    # attempt 2: 2.0 * 2^1 = 4.0
    assert strategy.calculate_backoff(2) == 4.0


def test_execute_with_retry_sync_success_first_try():
    """测试第一次就成功的情况"""
    config = RetryConfig()
    strategy = RetryStrategy(config)

    def success_func():
        return "success"

    result = execute_with_retry_sync(success_func, strategy)

    assert result.success is True
    assert result.result == "success"
    assert len(result.attempts) == 0  # 没有重试


def test_execute_with_retry_sync_success_after_retries():
    """测试重试后成功的情况"""
    config = RetryConfig(default_max_retries=3, default_backoff_base=0.01)
    strategy = RetryStrategy(config)

    call_count = 0

    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise NetworkError("temporary failure")
        return "success"

    result = execute_with_retry_sync(flaky_func, strategy)

    assert result.success is True
    assert result.result == "success"
    assert len(result.attempts) == 2  # 失败了 2 次
    assert call_count == 3  # 总共调用了 3 次


def test_execute_with_retry_sync_failure_after_max_retries():
    """测试达到最大重试次数后失败"""
    config = RetryConfig(default_max_retries=2, default_backoff_base=0.01)
    strategy = RetryStrategy(config)

    def always_fail():
        raise NetworkError("persistent failure")

    result = execute_with_retry_sync(always_fail, strategy)

    assert result.success is False
    assert "NetworkError" in result.error
    # max_retries=2 意味着最多重试 2 次,所以 attempts 应该是 2
    assert len(result.attempts) == 2


def test_execute_with_retry_sync_no_retry_for_auth_error():
    """测试认证错误不重试"""
    config = RetryConfig(
        default_max_retries=3,
        default_backoff_base=0.01,
        non_retryable_errors=["AuthenticationError"]
    )
    strategy = RetryStrategy(config)

    def auth_fail():
        raise AuthenticationError("invalid credentials")

    result = execute_with_retry_sync(auth_fail, strategy)

    assert result.success is False
    assert "AuthenticationError" in result.error
    assert len(result.attempts) == 1  # 只尝试了 1 次,没有重试


def test_retry_attempts_recorded():
    """测试重试尝试被正确记录"""
    config = RetryConfig(default_max_retries=2, default_backoff_base=0.01)
    strategy = RetryStrategy(config)

    def always_fail():
        raise NetworkError("test error")

    result = execute_with_retry_sync(always_fail, strategy)

    # max_retries=2, 所以应该有 2 次失败尝试
    assert len(result.attempts) == 2

    # 检查每次尝试的记录
    for i, attempt in enumerate(result.attempts, 1):
        assert attempt.attempt == i
        assert attempt.error == "test error"
        assert attempt.error_type == "NetworkError"
        assert attempt.backoff_seconds >= 0


@pytest.mark.asyncio
async def test_execute_with_retry_async():
    """测试异步函数的重试"""
    config = RetryConfig(default_max_retries=2, default_backoff_base=0.01)
    strategy = RetryStrategy(config)

    call_count = 0

    async def async_flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise NetworkError("temporary failure")
        return "async success"

    result = await strategy.execute_with_retry(async_flaky_func)

    assert result.success is True
    assert result.result == "async success"
    assert len(result.attempts) == 1
    assert call_count == 2


def test_retry_disabled():
    """测试禁用重试功能"""
    config = RetryConfig(enabled=False)
    strategy = RetryStrategy(config)

    def always_fail():
        raise NetworkError("test error")

    result = execute_with_retry_sync(always_fail, strategy)

    assert result.success is False
    assert len(result.attempts) == 1  # 只尝试了 1 次


def test_custom_max_retries():
    """测试自定义最大重试次数"""
    config = RetryConfig(default_max_retries=3, default_backoff_base=0.01)
    strategy = RetryStrategy(config)

    def always_fail():
        raise NetworkError("test error")

    # 覆盖为只重试 1 次
    result = execute_with_retry_sync(always_fail, strategy, max_retries=1)

    assert result.success is False
    assert len(result.attempts) == 2  # 初始 + 1 次重试
