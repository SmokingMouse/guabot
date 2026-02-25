from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import logging
import os

from .agent import AgentConfig, AgentExecutor, ExecutionTrace
from .capabilities import CapabilityRegistry, default_registry
from .config import AppConfig, LLMConfig
from .memory import Message, MemoryStore


@dataclass
class IncomingMessage:
    """来自 IM 渠道的标准化输入。"""

    channel_type: str
    conversation_id: str
    user_id: str
    text: str


@dataclass
class OutgoingMessage:
    """准备发送回 IM 渠道的输出。"""

    channel_type: str
    conversation_id: str
    text: str
    # 未来可加入附加元数据（如 @ 对象、按钮等）


@dataclass
class PipelineContext:
    """WaitingForMsg -> AgentExec -> SendMsg 所需的上下文。"""

    app_config: AppConfig
    memory_store: MemoryStore
    agent_executor: AgentExecutor


logger = logging.getLogger(__name__)


def log_execution_trace(conversation_id: str, trace: ExecutionTrace) -> None:
    """记录一次 LLM + Tools/Skills 执行的结构化轨迹日志。

    该函数集中封装日志格式，便于后续在不同调用点复用和演进。
    """

    try:  # pragma: no cover - 日志本身不需要单独测试
        logger.info(
            "llm_tools_execution",
            extra={
                "conversation_id": conversation_id,
                "trace": trace.model_dump(),
            },
        )
    except Exception:
        # 日志失败不应影响主流程
        logger.debug("failed to log execution trace", exc_info=True)


def build_default_pipeline() -> PipelineContext:
    """构造一个带默认配置/记忆/能力的 PipelineContext。

    适合本地开发与测试使用。
    """

    # 优先从配置文件加载，如果不存在则使用最小默认配置
    config_path = os.getenv("GUABOT_CONFIG", "guabot.toml")
    if Path(config_path).is_file():
        app_cfg = AppConfig.from_toml(config_path)
    else:
        app_cfg = AppConfig.minimal()
    memory = MemoryStore(default_window_size=20)
    registry: CapabilityRegistry = default_registry()

    # LLM 配置优先读取配置文件中的 llm 段，若缺失则回退到环境变量
    llm_cfg = getattr(app_cfg, "llm", None) or LLMConfig.from_env(prefix="GUABOT_LLM_")
    agent_cfg = AgentConfig(
        endpoint=llm_cfg.endpoint if llm_cfg else None,
        api_key=llm_cfg.api_key if llm_cfg else None,
        model=llm_cfg.model if llm_cfg else None,
        timeout=llm_cfg.timeout if llm_cfg else 10.0,
    )
    executor = AgentExecutor(agent_cfg, registry)
    return PipelineContext(app_config=app_cfg, memory_store=memory, agent_executor=executor)


def handle_incoming_message(context: PipelineContext, incoming: IncomingMessage) -> OutgoingMessage:
    """执行 WaitingForMsg -> AgentExec -> SendMsg 主流程。

    - WaitingForMsg: 标准化 IM 消息并写入会话记忆；
    - AgentExec: 读取最近 N 条历史，调用 AgentExecutor；
    - SendMsg: 返回一条 OutgoingMessage，由上层 IM 适配器负责真正发送。
    """

    channel_cfg = context.app_config.channels.get(incoming.channel_type)
    window_size = channel_cfg.default_memory_window if channel_cfg else 20

    # WaitingForMsg: 记录用户消息
    user_msg = Message(conversation_id=incoming.conversation_id, sender="user", text=incoming.text)
    context.memory_store.append(user_msg, window_size=window_size)

    history = list(context.memory_store.history(incoming.conversation_id))

    # AgentExec: 用 AgentExecutor 生成回复，并获取执行轨迹
    reply_text, trace = context.agent_executor.run_with_trace(history=history, latest=user_msg)

    # 记录执行轨迹，便于后续调试与观测
    log_execution_trace(incoming.conversation_id, trace)

    # SendMsg: 返回统一结构，真正的 IM 发送由调用方负责
    return OutgoingMessage(
        channel_type=incoming.channel_type,
        conversation_id=incoming.conversation_id,
        text=reply_text,
    )
