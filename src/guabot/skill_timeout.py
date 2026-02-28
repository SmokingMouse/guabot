from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class TimeoutConfig:
    """超时配置"""

    enabled: bool = True
    default_timeout: float = 60.0  # 秒
    grace_period: float = 5.0      # 优雅终止等待时间


@dataclass
class TimeoutResult:
    """超时执行结果"""

    success: bool
    result: Any = None
    error: Optional[str] = None
    timed_out: bool = False
    execution_time: float = 0.0
    timeout_threshold: float = 0.0


class TimeoutError(Exception):
    """超时异常"""
    pass


class TimeoutManager:
    """超时管理器"""

    def __init__(self, config: TimeoutConfig):
        self.config = config

    async def execute_with_timeout(
        self,
        func: Callable[..., Any],
        *args: Any,
        timeout: float | None = None,
        **kwargs: Any
    ) -> TimeoutResult:
        """执行函数并设置超时

        Args:
            func: 要执行的函数 (可以是同步或异步)
            *args: 函数参数
            timeout: 超时时间 (秒),None 使用默认值
            **kwargs: 函数关键字参数

        Returns:
            TimeoutResult
        """
        if not self.config.enabled:
            # 超时功能禁用,直接执行
            start_time = time.time()
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                return TimeoutResult(
                    success=True,
                    result=result,
                    execution_time=time.time() - start_time
                )
            except Exception as e:
                return TimeoutResult(
                    success=False,
                    error=str(e),
                    execution_time=time.time() - start_time
                )

        timeout_seconds = timeout if timeout is not None else self.config.default_timeout
        start_time = time.time()

        try:
            # 使用 asyncio.wait_for 实现超时
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_seconds
                )
            else:
                # 同步函数需要在 executor 中运行
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: func(*args, **kwargs)),
                    timeout=timeout_seconds
                )

            return TimeoutResult(
                success=True,
                result=result,
                execution_time=time.time() - start_time,
                timeout_threshold=timeout_seconds
            )

        except asyncio.TimeoutError:
            # 超时
            return TimeoutResult(
                success=False,
                error=f"Execution timed out after {timeout_seconds}s",
                timed_out=True,
                execution_time=time.time() - start_time,
                timeout_threshold=timeout_seconds
            )

        except Exception as e:
            # 其他错误
            return TimeoutResult(
                success=False,
                error=f"{type(e).__name__}: {str(e)}",
                execution_time=time.time() - start_time,
                timeout_threshold=timeout_seconds
            )


def execute_with_timeout_sync(
    func: Callable[..., Any],
    timeout_manager: TimeoutManager,
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any
) -> TimeoutResult:
    """同步版本的超时执行 (用于非异步环境)

    Args:
        func: 要执行的同步函数
        timeout_manager: 超时管理器
        *args: 函数参数
        timeout: 超时时间
        **kwargs: 函数关键字参数

    Returns:
        TimeoutResult
    """
    # 创建新的事件循环来运行异步函数
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            timeout_manager.execute_with_timeout(func, *args, timeout=timeout, **kwargs)
        )
    finally:
        loop.close()
