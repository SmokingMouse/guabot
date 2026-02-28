from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import logging
import os

from .agent import AgentConfig, AgentExecutor, ExecutionTrace, build_session_meta
from .channels.base import ChannelMessage
from .tools.registry import CapabilityRegistry, default_registry
from .config import AppConfig, LLMConfig, McpServerConfig
from .context_compression import ContextCompressor, CompressionConfig
from .memory import ExecutionTraceStore, Message, MemoryStore
from .task_state import TaskStateStore, extract_action_entries, render_task_state_block
from .tracing import write_trace_turn


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
    task_state_store: TaskStateStore
    context_compressor: ContextCompressor

    def reload_mcp(self, server_id: str) -> dict:
        """热重载指定 MCP server（停旧进程 → 启新进程 → 重新注册工具）。"""
        from .mcp.loader import reload_mcp_server
        registry = self.agent_executor._capabilities
        return reload_mcp_server(server_id, self.app_config, registry)

    def add_mcp_server(self, server_id: str, command: list[str], env: dict | None = None) -> dict:
        """运行时新增一个 MCP server（不需要重启 bot）。"""
        from .mcp.loader import _load_one
        srv = McpServerConfig(id=server_id, command=command, env=env or {})
        # 追加到 config，使 reload_mcp 之后也能找到
        self.app_config.mcp_servers = [
            s for s in self.app_config.mcp_servers if s.id != server_id
        ] + [srv]
        registry = self.agent_executor._capabilities
        ok = _load_one(srv, registry)
        if not ok:
            return {"error": f"server '{server_id}' failed to start"}
        tools = [n for n in registry.available_names() if n.startswith(f"{server_id}.")]
        return {"server_id": server_id, "tools": tools}

    def remove_mcp_server(self, server_id: str) -> dict:
        """运行时移除一个 MCP server。"""
        from .mcp.loader import unload_mcp_server
        registry = self.agent_executor._capabilities
        unload_mcp_server(server_id, registry)
        self.app_config.mcp_servers = [
            s for s in self.app_config.mcp_servers if s.id != server_id
        ]
        return {"server_id": server_id, "unloaded": True}

    def reload_skills(self) -> dict:
        """重新扫描 skills_dir，返回当前已安装的 skill 列表（skills 本身已是热加载，此方法供确认用）。"""
        registry = self.agent_executor._capabilities
        result = registry.invoke("skill.list", {})
        return result


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


def _start_memory_scheduler(app_cfg: AppConfig) -> None:
    """启动后台定时线程，定期运行 memory-extractor 和 profile-updater。"""
    import subprocess
    import sys
    import threading
    import time

    default_dirs = getattr(app_cfg.skills, "default_dirs", []) if hasattr(app_cfg, "skills") else []
    skills_dir = default_dirs[0] if default_dirs else ".guabot/skills"
    extractor_interval = app_cfg.memory_extractor_interval
    profile_interval = app_cfg.profile_updater_interval

    if not extractor_interval and not profile_interval:
        return

    def _run_skill(skill_name: str) -> None:
        script = Path(skills_dir) / skill_name / "scripts" / "run.py"
        if not script.exists():
            logger.warning("memory scheduler: script not found: %s", script)
            return
        try:
            result = subprocess.run(
                [sys.executable, str(script)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.warning("memory scheduler: %s exited %d: %s", skill_name, result.returncode, result.stderr[:200])
            else:
                logger.info("memory scheduler: %s done: %s", skill_name, result.stdout.strip()[:200])
        except Exception as exc:
            logger.warning("memory scheduler: %s failed: %s", skill_name, exc)

    def _loop(skill_name: str, interval_minutes: int) -> None:
        while True:
            time.sleep(interval_minutes * 60)
            _run_skill(skill_name)

    if extractor_interval:
        threading.Thread(target=_loop, args=("memory-extractor", extractor_interval), daemon=True).start()
        logger.info("memory scheduler: memory-extractor every %d min", extractor_interval)

    if profile_interval:
        threading.Thread(target=_loop, args=("profile-updater", profile_interval), daemon=True).start()
        logger.info("memory scheduler: profile-updater every %d min", profile_interval)


def build_default_pipeline() -> PipelineContext:
    """构造一个带默认配置/记忆/能力的 PipelineContext。"""

    config_path = os.getenv("GUABOT_CONFIG", "guabot.toml")
    if Path(config_path).is_file():
        app_cfg = AppConfig.from_toml(config_path)
        if app_cfg.memory_dir and not os.getenv("GUABOT_MEMORY_DIR"):
            os.environ["GUABOT_MEMORY_DIR"] = app_cfg.memory_dir
    else:
        app_cfg = AppConfig.minimal()

    memory = MemoryStore(default_window_size=20)
    trace_store = ExecutionTraceStore()
    task_state_store = TaskStateStore(ttl_seconds=app_cfg.task_state_ttl_seconds)
    context_compressor = ContextCompressor(app_cfg.context_compression)
    registry: CapabilityRegistry = default_registry(app_cfg)

    llm_cfg = getattr(app_cfg, "llm", None) or LLMConfig.from_env(prefix="GUABOT_LLM_")
    agent_cfg = AgentConfig(
        endpoint=llm_cfg.endpoint if llm_cfg else None,
        api_key=llm_cfg.api_key if llm_cfg else None,
        model=llm_cfg.model if llm_cfg else None,
        timeout=llm_cfg.timeout if llm_cfg else 10.0,
    )
    executor = AgentExecutor(agent_cfg, registry)
    ctx = PipelineContext(
        app_config=app_cfg,
        memory_store=memory,
        agent_executor=executor,
        trace_store=trace_store,
        task_state_store=task_state_store,
        context_compressor=context_compressor,
    )

    # 注入 pipeline context，使 HotReloadTool 可以调用 reload_mcp / reload_skills
    hot_reload = registry.get("tool.hot_reload")
    if hot_reload is not None:
        hot_reload._pipeline_context = ctx  # type: ignore[attr-defined]

    _start_memory_scheduler(app_cfg)

    return ctx


def handle_incoming_message(context: PipelineContext, incoming: IncomingMessage) -> OutgoingMessage:
    """执行 WaitingForMsg -> AgentExec -> SendMsg 主流程。"""

    channel_cfg = context.app_config.channels.get(incoming.channel_type)
    window_size = channel_cfg.default_memory_window if channel_cfg else 20

    previous_history = list(context.memory_store.history(incoming.conversation_id))
    previous_len = len(previous_history)
    user_msg = Message(conversation_id=incoming.conversation_id, sender="user", text=incoming.text)
    context.memory_store.append(user_msg, window_size=window_size)
    history = list(context.memory_store.history(incoming.conversation_id))
    dropped_count = max(0, previous_len + 1 - len(history))

    session_meta = build_session_meta(
        channel=incoming.channel_type,
        conversation_id=incoming.conversation_id,
        user_id=incoming.user_id,
        extra={},
    )
    existing_state = context.task_state_store.get(incoming.conversation_id)
    task_state_block = render_task_state_block(existing_state, max_steps=10)
    turn_index = len(context.trace_store.list_by_session(incoming.conversation_id)) + 1

    reply_text, trace = context.agent_executor.run_with_trace(
        history=history,
        latest=user_msg,
        session_meta=session_meta,
        task_state_block=task_state_block,
    )

    context.trace_store.save(trace)
    context.task_state_store.update(
        incoming.conversation_id, extract_action_entries(trace, turn=turn_index)
    )
    log_execution_trace(incoming.conversation_id, trace)

    has_tool_failure = any(inv.status != "success" for inv in trace.tool_invocations)
    if has_tool_failure:
        message_status = "failed"
    elif dropped_count > 0:
        message_status = "compressed"
    else:
        message_status = "active"
    context_event = (
        {
            "type": "compressed",
            "detail": f"context window trimmed; dropped_messages={dropped_count}",
        }
        if dropped_count > 0
        else None
    )
    try:
        write_trace_turn(
            conversation_id=incoming.conversation_id,
            channel=incoming.channel_type,
            user_id=incoming.user_id,
            user_text=incoming.text,
            assistant_reply=reply_text,
            tool_invocations=trace.tool_invocations,
            llm_rounds=trace.llm_rounds,
            message_status=message_status,
            context_event=context_event,
            trace_id=trace.id,
        )
    except Exception:  # pragma: no cover
        logger.debug("failed to write trace viewer JSON", exc_info=True)

    # Layer 1 异步写盘（不阻塞响应）
    import threading as _threading
    from .memory_fs import append_conversation_log as _append_log
    _threading.Thread(
        target=_append_log,
        kwargs=dict(
            conversation_id=incoming.conversation_id,
            channel=incoming.channel_type,
            user_id=incoming.user_id,
            user_text=incoming.text,
            agent_reply=reply_text,
            tool_invocations=trace.tool_invocations,
        ),
        daemon=True,
    ).start()

    return OutgoingMessage(
        channel_type=incoming.channel_type,
        conversation_id=incoming.conversation_id,
        text=reply_text,
        trace_id=trace.id,
    )


def handle_channel_message(context: PipelineContext, message: ChannelMessage) -> OutgoingMessage:
    """Convert a channel message into the standard pipeline flow."""

    incoming = IncomingMessage(
        channel_type=message.channel_type,
        conversation_id=message.conversation_id,
        user_id=message.user_id,
        text=message.text,
    )
    return handle_incoming_message(context, incoming)
