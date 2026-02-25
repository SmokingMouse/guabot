from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import logging
import os

from .agent import AgentConfig, AgentExecutor, ExecutionTrace, build_session_meta
from .capabilities import CapabilityRegistry, default_registry
from .config import AppConfig, LLMConfig
from .memory import ExecutionTraceStore, Message, MemoryStore


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
    trace_id: str | None = None


@dataclass
class PipelineContext:
    """WaitingForMsg -> AgentExec -> SendMsg 所需的上下文。"""

    app_config: AppConfig
    memory_store: MemoryStore
    agent_executor: AgentExecutor
    trace_store: ExecutionTraceStore


logger = logging.getLogger(__name__)


def log_execution_trace(conversation_id: str, trace: ExecutionTrace) -> None:
    """记录一次 LLM + Tools/Skills 执行的结构化轨迹日志。"""

    try:  # pragma: no cover
        logger.info(
            "llm_tools_execution",
            extra={
                "conversation_id": conversation_id,
                "trace": trace.model_dump(),
            },
        )
    except Exception:
        logger.debug("failed to log execution trace", exc_info=True)


def build_default_pipeline() -> PipelineContext:
    """构造一个带默认配置/记忆/能力的 PipelineContext。"""

    config_path = os.getenv("GUABOT_CONFIG", "guabot.toml")
    if Path(config_path).is_file():
        app_cfg = AppConfig.from_toml(config_path)
    else:
        app_cfg = AppConfig.minimal()

    memory = MemoryStore(default_window_size=20)
    trace_store = ExecutionTraceStore()
    registry: CapabilityRegistry = default_registry()

    llm_cfg = getattr(app_cfg, "llm", None) or LLMConfig.from_env(prefix="GUABOT_LLM_")
    agent_cfg = AgentConfig(
        endpoint=llm_cfg.endpoint if llm_cfg else None,
        api_key=llm_cfg.api_key if llm_cfg else None,
        model=llm_cfg.model if llm_cfg else None,
        timeout=llm_cfg.timeout if llm_cfg else 10.0,
    )
    executor = AgentExecutor(agent_cfg, registry)
    return PipelineContext(app_config=app_cfg, memory_store=memory, agent_executor=executor, trace_store=trace_store)


def handle_incoming_message(context: PipelineContext, incoming: IncomingMessage) -> OutgoingMessage:
    """执行 WaitingForMsg -> AgentExec -> SendMsg 主流程。"""

    channel_cfg = context.app_config.channels.get(incoming.channel_type)
    window_size = channel_cfg.default_memory_window if channel_cfg else 20

    user_msg = Message(conversation_id=incoming.conversation_id, sender="user", text=incoming.text)
    context.memory_store.append(user_msg, window_size=window_size)
    history = list(context.memory_store.history(incoming.conversation_id))

    session_meta = build_session_meta(
        channel=incoming.channel_type,
        conversation_id=incoming.conversation_id,
        user_id=incoming.user_id,
        extra={},
    )

    reply_text, trace = context.agent_executor.run_with_trace(
        history=history,
        latest=user_msg,
        session_meta=session_meta,
    )

    context.trace_store.save(trace)
    log_execution_trace(incoming.conversation_id, trace)

    return OutgoingMessage(
        channel_type=incoming.channel_type,
        conversation_id=incoming.conversation_id,
        text=reply_text,
        trace_id=trace.id,
    )
