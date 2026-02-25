from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json

from openai import OpenAI
from pydantic import BaseModel

from .capabilities import CapabilityRegistry
from .memory import Message

@dataclass
class AgentConfig:
    """与具体大模型/Agent 交互相关的配置占位符。

    首版仅保留最小字段，实际调用逻辑可以在后续特性中补充。
    """

    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float = 10.0


class LLMContext(BaseModel):
    """单次 LLM 决策可见的上下文。

    为保持简洁，这里只保留会话 ID、当前消息和最近若干条历史文本。
    """

    conversation_id: str
    user_message: str
    history: List[str]


class ToolStep(BaseModel):
    """单步工具调用计划。"""

    capability_name: str
    arguments: Dict[str, Any] = {}


class ToolPlan(BaseModel):
    """工具调用计划，由“LLM 决策层”产出。"""

    steps: List[ToolStep] = []


class ToolInvocationTrace(BaseModel):
    """单次工具调用的执行轨迹摘要。"""

    capability_name: str
    status: str
    latency_ms: float
    result_summary: str


class ExecutionTrace(BaseModel):
    """一次 LLM + Tools 执行过程的关键轨迹。"""

    conversation_id: str
    user_message: str
    tool_plan: Optional[ToolPlan] = None
    tool_invocations: List[ToolInvocationTrace] = []
    final_reply_summary: str


class AgentExecutor:
    """负责执行 Agent 调用的简单执行器。

    当前实现不会真正访问外部 LLM，而是基于能力调用给出一个可观测的占位回复，
    目的是让脚手架主流程可以被端到端验证。
    """

    def __init__(self, config: AgentConfig, capabilities: CapabilityRegistry) -> None:
        self._config = config
        self._capabilities = capabilities
        self._last_trace: Optional[ExecutionTrace] = None

    @property
    def last_trace(self) -> Optional[ExecutionTrace]:  # pragma: no cover - 简单访问器
        return self._last_trace

    def _build_context(self, history: Iterable[Message], latest: Message) -> LLMContext:
        texts: List[str] = [m.text for m in history]
        return LLMContext(
            conversation_id=latest.conversation_id,
            user_message=latest.text,
            history=texts,
        )

    def _decide_tool_plan(self, ctx: LLMContext) -> Optional[ToolPlan]:
        """极简“LLM 决策”占位实现。

        在接入真实 LLM 之前，先用规则模拟：
        - 包含 "time" 或 "时间" 时，计划调用 time.now；
        - 否则不调用任何工具。
        """

        text = ctx.user_message.lower()
        if "time" in text or "时间" in text:
            return ToolPlan(steps=[ToolStep(capability_name="time.now", arguments={})])
        return None

    def _call_llm_for_plan(self, ctx: LLMContext) -> Tuple[Optional[ToolPlan], Optional[str]]:
        """使用 OpenAI function calling（tools）能力，让 LLM 决策是否调用工具。

        - 使用 chat.completions.create 的 tools 能力，而不是依赖 system prompt 手写协议；
        - 若模型选择调用工具，则从 tool_calls 中提取 ToolPlan；
        - 若模型不调用工具，则直接使用文本 content 作为回复。
        """

        if not self._config.api_key:
            return None, None

        client = OpenAI(
            api_key=self._config.api_key,
            base_url=self._config.endpoint or None,
        )

        caps_details = self._capabilities.available_details()

        # 将内部能力映射为 OpenAI function calling 的 tools 规范
        tool_schemas: Dict[str, Dict[str, Any]] = {
            "time.now": {
                "type": "object",
                "properties": {},
                "required": [],
            },
            "shell.bash": {
                "type": "object",
                "properties": {
                    "cmd": {
                        "type": "string",
                        "description": "要执行的 Bash 命令，例如 'ls -la' 或 'cat README.md'。",
                    }
                },
                "required": ["cmd"],
            },
            "fs.ls": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径，默认当前工作目录。",
                    }
                },
                "required": [],
            },
            "fs.read_file": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要读取内容的文件路径。",
                    }
                },
                "required": ["path"],
            },
        }

        tools: List[Dict[str, Any]] = []
        for cap in caps_details:
            name = cap["name"]
            schema = tool_schemas.get(name, {"type": "object", "properties": {}, "required": []})
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": cap["description"],
                        "parameters": schema,
                    },
                }
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "你是一个可以根据需要调用工具的助手。只有当调用工具有助于回答用户问题时，"
                    "才选择合适的工具，并为每个工具提供严格符合 JSON Schema 的参数。"
                    "如果不需要工具，也可以直接用自然语言回答。"
                ),
            },
            {
                "role": "user",
                "content": ctx.user_message,
            },
        ]

        try:
            response = client.chat.completions.create(
                model=self._config.model or "gpt-4.1-mini",
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0,
            )
        except Exception:
            return None, None

        msg = response.choices[0].message

        # 如果模型没有选择调用工具，则直接返回自然语言回复
        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            return None, msg.content or ""

        # 否则，将 tool_calls 映射为 ToolPlan
        steps: List[ToolStep] = []
        for tc in tool_calls:
            try:
                func = tc.function
                name = func.name
                args_str = func.arguments or "{}"
                args = json.loads(args_str)
            except Exception:
                continue
            steps.append(ToolStep(capability_name=name, arguments=args))

        if not steps:
            return None, msg.content or ""

        plan = ToolPlan(steps=steps)
        # 此处 msg.content 可能为空或为对工具调用的解释性内容，仍按 llm_reply 返回
        return plan, msg.content or ""

    def run_with_trace(self, history: Iterable[Message], latest: Message) -> tuple[str, ExecutionTrace]:
        """根据历史与最新消息生成回复，并返回执行轨迹。

        轨迹并不依赖具体 LLM 实现，后续接入真实 LLM 时可以替换
        `_decide_tool_plan` 与回复生成逻辑，但不会影响外部调用方式。
        """

        ctx = self._build_context(history, latest)

        llm_reply: Optional[str] = None
        plan: Optional[ToolPlan]

        # 只要配置了 API Key，就尝试通过 LLM 决策；未配置则完全走本地规则
        if self._config.api_key:
            print(f"调用 LLM 决策，上下文：{ctx}")
            plan, llm_reply = self._call_llm_for_plan(ctx)
            print(f"LLM 决策结果：计划={plan}，回复={llm_reply}")

            # 如果外部 LLM 不可用或未返回有效计划，则回退到本地规则决策
            if plan is None and llm_reply is None:
                plan = self._decide_tool_plan(ctx)
        else:
            plan = self._decide_tool_plan(ctx)

        invocations: List[ToolInvocationTrace] = []
        reply_text: str

        if plan and plan.steps:
            # 依次执行计划中的工具（首版不区分并行/串行）
            last_result: Optional[Dict[str, Any]] = None
            last_capability_name: Optional[str] = None

            for step in plan.steps:
                import time as _time

                start = _time.perf_counter()
                status = "success"
                result_summary = ""
                try:
                    result = self._capabilities.invoke(step.capability_name, step.arguments)
                    last_result = result
                    last_capability_name = step.capability_name
                    # 简化：只截取部分结果用于摘要
                    result_summary = str(result)
                except Exception as exc:  # pragma: no cover - 异常路径在后续扩展测试
                    status = "failed"
                    result_summary = f"error: {exc!r}"
                end = _time.perf_counter()

                invocations.append(
                    ToolInvocationTrace(
                        capability_name=step.capability_name,
                        status=status,
                        latency_ms=(end - start) * 1000,
                        result_summary=result_summary,
                    )
                )

            # 根据最后一次成功的工具调用构造人类可读回复
            if invocations and invocations[-1].status == "success" and last_capability_name is not None:
                if last_capability_name == "time.now":
                    # result_summary 是 str(result)，此处只做展示用途
                    tool_reply = f"当前时间（示例能力）: {invocations[-1].result_summary}"
                elif last_capability_name == "fs.ls" and isinstance(last_result, dict):
                    entries = last_result.get("entries") or []
                    total = len(entries)
                    sample_names = [e.get("name", "?") for e in entries[:5]]
                    sample_str = ", ".join(sample_names) if sample_names else "(空目录)"
                    tool_reply = f"目录共有 {total} 个条目，示例：{sample_str}"
                else:
                    # 通用兜底：直接展示摘要字符串的前缀
                    summary = invocations[-1].result_summary
                    if len(summary) > 200:
                        summary = summary[:200] + "..."
                    tool_reply = f"工具 {last_capability_name} 调用成功，摘要：{summary}"

                if llm_reply:
                    reply_text = f"{llm_reply}\n\n{tool_reply}"
                else:
                    reply_text = tool_reply
            else:
                reply_text = f"[demo] 工具调用完成，但结果不可用"
        else:
            # 默认行为：优先使用 LLM 回复，其次使用 echo 占位
            if llm_reply:
                reply_text = llm_reply
            else:
                reply_text = f"[demo] 你刚才说：{latest.text}"

        trace = ExecutionTrace(
            conversation_id=latest.conversation_id,
            user_message=latest.text,
            tool_plan=plan,
            tool_invocations=invocations,
            final_reply_summary=reply_text,
        )
        self._last_trace = trace
        return reply_text, trace

    def run(self, history: Iterable[Message], latest: Message) -> str:
        """向后兼容的旧接口：仅返回回复文本。"""

        reply, _trace = self.run_with_trace(history=history, latest=latest)
        return reply
