from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class RetryConfig:
    """重试配置"""

    enabled: bool = True
    default_max_retries: int = 3
    default_backoff_base: float = 1.0  # 秒
    max_total_retry_time: float = 30.0  # 秒
    retryable_errors: List[str] = field(default_factory=lambda: [
        "NetworkError", "TimeoutError", "RateLimitError", "ConnectionError"
    ])
    non_retryable_errors: List[str] = field(default_factory=lambda: [
        "AuthenticationError", "InvalidInputError", "PermissionError"
    ])


@dataclass
class RetryAttempt:
    """单次重试尝试记录"""

    attempt: int
    error: str
    error_type: str
    backoff_seconds: float
    timestamp: float


@dataclass
class RetryResult:
    """重试结果"""

    success: bool
    result: Any = None
    error: Optional[str] = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    total_time: float = 0.0


class RetryStrategy:
    """重试策略"""

    def __init__(self, config: RetryConfig):
        self.config = config

    def should_retry(self, error: Exception, attempt: int, elapsed_time: float) -> bool:
        """判断是否应该重试

        Args:
            error: 异常对象
            attempt: 当前尝试次数 (从 1 开始)
            elapsed_time: 已经过的时间

        Returns:
            是否应该重试
        """
        if not self.config.enabled:
            return False

        # 检查是否超过最大重试次数
        if attempt >= self.config.default_max_retries:
            return False

        # 检查是否超过总时间限制
        if elapsed_time >= self.config.max_total_retry_time:
            return False

        # 检查错误类型
        error_type = type(error).__name__
        if error_type in self.config.non_retryable_errors:
            return False

        # 如果在可重试列表中,或者不在不可重试列表中,则重试
        if error_type in self.config.retryable_errors:
            return True

        # 默认对未知错误类型也重试 (保守策略)
        return True

    def calculate_backoff(self, attempt: int, backoff_base: float | None = None) -> float:
        """计算退避时间 (指数退避)

        Args:
            attempt: 当前尝试次数 (从 1 开始)
            backoff_base: 退避基数,默认使用配置值

        Returns:
            退避秒数
        """
        base = backoff_base if backoff_base is not None else self.config.default_backoff_base
        # 指数退避: base * (2 ^ (attempt - 1))
        # attempt 1 -> base * 1 = base
        # attempt 2 -> base * 2
        # attempt 3 -> base * 4
        return base * (2 ** (attempt - 1))

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args: Any,
        max_retries: int | None = None,
        backoff_base: float | None = None,
        **kwargs: Any
    ) -> RetryResult:
        """执行函数并在失败时重试

        Args:
            func: 要执行的函数 (可以是同步或异步)
            *args: 函数参数
            max_retries: 最大重试次数 (覆盖配置)
            backoff_base: 退避基数 (覆盖配置)
            **kwargs: 函数关键字参数

        Returns:
            RetryResult
        """
        start_time = time.time()
        attempts: List[RetryAttempt] = []
        max_retries_to_use = max_retries if max_retries is not None else self.config.default_max_retries

        for attempt in range(1, max_retries_to_use + 2):  # +2 因为第一次不算重试
            try:
                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # 成功
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_time=time.time() - start_time
                )

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                elapsed_time = time.time() - start_time

                # 记录这次尝试
                backoff = self.calculate_backoff(attempt, backoff_base) if attempt <= max_retries_to_use else 0
                attempts.append(RetryAttempt(
                    attempt=attempt,
                    error=error_msg,
                    error_type=error_type,
                    backoff_seconds=backoff,
                    timestamp=time.time()
                ))

                # 判断是否应该重试
                if not self.should_retry(e, attempt, elapsed_time):
                    # 不重试,返回失败
                    return RetryResult(
                        success=False,
                        error=f"{error_type}: {error_msg}",
                        attempts=attempts,
                        total_time=elapsed_time
                    )

                # 等待退避时间
                if backoff > 0:
                    await asyncio.sleep(backoff)

        # 超过最大重试次数
        return RetryResult(
            success=False,
            error=f"Max retries ({max_retries_to_use}) exceeded",
            attempts=attempts,
            total_time=time.time() - start_time
        )


def execute_with_retry_sync(
    func: Callable[..., Any],
    retry_strategy: RetryStrategy,
    *args: Any,
    max_retries: int | None = None,
    backoff_base: float | None = None,
    **kwargs: Any
) -> RetryResult:
    """同步版本的重试执行 (用于非异步环境)

    Args:
        func: 要执行的同步函数
        retry_strategy: 重试策略
        *args: 函数参数
        max_retries: 最大重试次数
        backoff_base: 退避基数
        **kwargs: 函数关键字参数

    Returns:
        RetryResult
    """
    start_time = time.time()
    attempts: List[RetryAttempt] = []
    max_retries_to_use = max_retries if max_retries is not None else retry_strategy.config.default_max_retries

    for attempt in range(1, max_retries_to_use + 2):
        try:
            result = func(*args, **kwargs)
            return RetryResult(
                success=True,
                result=result,
                attempts=attempts,
                total_time=time.time() - start_time
            )

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            elapsed_time = time.time() - start_time

            backoff = retry_strategy.calculate_backoff(attempt, backoff_base) if attempt <= max_retries_to_use else 0
            attempts.append(RetryAttempt(
                attempt=attempt,
                error=error_msg,
                error_type=error_type,
                backoff_seconds=backoff,
                timestamp=time.time()
            ))

            if not retry_strategy.should_retry(e, attempt, elapsed_time):
                return RetryResult(
                    success=False,
                    error=f"{error_type}: {error_msg}",
                    attempts=attempts,
                    total_time=elapsed_time
                )

            if backoff > 0:
                time.sleep(backoff)

    return RetryResult(
        success=False,
        error=f"Max retries ({max_retries_to_use}) exceeded",
        attempts=attempts,
        total_time=time.time() - start_time
    )
