from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from .capabilities import CapabilityRegistry
from .memory import Message


@dataclass
class AgentConfig:
    """与具体大模型/Agent 交互相关的配置。"""

    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float = 10.0


@dataclass
class SessionMeta:
    """渠道会话封装，统一描述一次请求所属会话。"""

    session_id: str
    channel: str
    user_id: str
    extra: Dict[str, Any] | None = None


def build_session_meta(
    channel: str,
    conversation_id: str,
    user_id: str,
    extra: Dict[str, Any] | None = None,
) -> SessionMeta:
    """从 IM 输入构建 SessionMeta。"""

    return SessionMeta(
        session_id=conversation_id,
        channel=channel,
        user_id=user_id,
        extra=extra or {},
    )


class LLMContext(BaseModel):
    """单次 LLM 决策可见的上下文。"""

    id: str
    user_message: str
    history: List[str]
    available_capabilities: List[Dict[str, Any]]
    channel: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolStep(BaseModel):
    """单步工具调用计划。"""

    step_id: str = Field(default_factory=lambda: f"step-{uuid.uuid4().hex[:8]}")
    capability_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)


class ToolPlan(BaseModel):
    """工具调用计划，由决策层产出。"""

    id: str = Field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    session_id: str
    llm_request_id: str = Field(default_factory=lambda: f"llm-{uuid.uuid4().hex[:8]}")
    steps: List[ToolStep] = Field(default_factory=list)
    max_parallelism: int = 1
    notes: str | None = None


class ToolInvocationTrace(BaseModel):
    """单次工具调用轨迹摘要。"""

    step_id: str
    capability_name: str
    status: str
    latency_ms: float
    result_summary: str


class LLMRoundTrace(BaseModel):
    """单轮 LLM 交互轨迹。"""

    round_index: int
    request_messages: List[Dict[str, Any]] = Field(default_factory=list)
    assistant_content: str = ""
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)


class ExecutionTrace(BaseModel):
    """一次 LLM + Tools/Skills 执行过程的关键轨迹。"""

    id: str = Field(default_factory=lambda: f"trace-{uuid.uuid4().hex[:10]}")
    session_id: str
    channel: str
    user_message: str
    tool_plan: Optional[ToolPlan] = None
    tool_invocations: List[ToolInvocationTrace] = Field(default_factory=list)
    llm_rounds: List[LLMRoundTrace] = Field(default_factory=list)
    final_reply_summary: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AgentExecutor:
    """负责执行 Agent 调用的简单执行器。"""

    def __init__(self, config: AgentConfig, capabilities: CapabilityRegistry) -> None:
        self._config = config
        self._capabilities = capabilities
        self._last_trace: Optional[ExecutionTrace] = None

    @property
    def last_trace(self) -> Optional[ExecutionTrace]:  # pragma: no cover
        return self._last_trace

    def _build_context(
        self, history: Iterable[Message], latest: Message, session_meta: SessionMeta
    ) -> LLMContext:
        return LLMContext(
            id=session_meta.session_id,
            user_message=latest.text,
            history=[m.text for m in history],
            available_capabilities=self._capabilities.available_descriptors(
                llm_only=True
            ),
            channel=session_meta.channel,
            metadata={"user_id": session_meta.user_id, **(session_meta.extra or {})},
        )

    def _decide_tool_plan(
        self, ctx: LLMContext
    ) -> tuple[Optional[ToolPlan], Optional[str]]:
        """本地规则决策，作为无 LLM 或 LLM 失败时兜底。"""

        text = ctx.user_message.lower()

        if "笑话" in text or "joke" in text:
            return None, "为什么程序员总分不清万圣节和圣诞节？因为 Oct 31 == Dec 25。"

        need_time = "time" in text or "时间" in text
        need_error = "error" in text or "错误数" in text or "错误数量" in text
        need_version = "version" in text or "版本" in text

        if need_error and need_version:
            step1 = ToolStep(
                capability_name="skill.error_count", arguments={"service": "core-api"}
            )
            version_args: Dict[str, Any] = {"service": "core-api"}
            if "版本不可用" in ctx.user_message or "version unavailable" in text:
                version_args["unavailable"] = True
            step2 = ToolStep(
                capability_name="skill.version_info",
                arguments=version_args,
                depends_on=[step1.step_id],
            )
            return ToolPlan(
                session_id=ctx.id, steps=[step1, step2], notes="查询错误数与版本并总结"
            ), None

        if need_error:
            step = ToolStep(
                capability_name="skill.error_count", arguments={"service": "core-api"}
            )
            return ToolPlan(session_id=ctx.id, steps=[step], notes="查询错误数"), None

        if need_version:
            args: Dict[str, Any] = {"service": "core-api"}
            if "版本不可用" in ctx.user_message or "version unavailable" in text:
                args["unavailable"] = True
            step = ToolStep(capability_name="skill.version_info", arguments=args)
            return ToolPlan(session_id=ctx.id, steps=[step], notes="查询版本信息"), None

        if need_time:
            step = ToolStep(capability_name="time.now", arguments={})
            return ToolPlan(session_id=ctx.id, steps=[step], notes="查询当前时间"), None

        return None, None

    def _run_llm_with_tool_loop(
        self, ctx: LLMContext
    ) -> tuple[
        Optional[str], Optional[ToolPlan], List[ToolInvocationTrace], List[LLMRoundTrace]
    ]:
        """使用工具调用循环驱动执行。

        每轮将完整上下文和工具描述提供给 LLM：
        - 若返回普通消息（无 tool_calls），流程结束；
        - 若返回 tool_calls，逐个调用能力，将 tool result 追加到上下文后继续下一轮。
        """

        if not self._config.api_key:
            return None, None, [], []

        client = OpenAI(
            api_key=self._config.api_key, base_url=self._config.endpoint or None
        )
        caps_details = self._capabilities.available_descriptors(llm_only=True)

        tools: List[Dict[str, Any]] = []
        for cap in caps_details:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": cap["name"],
                        "description": cap["description"],
                        "parameters": cap["input_schema"],
                    },
                }
            )

        history_summary = "\n".join(ctx.history[-10:])
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "你是一个可以根据需要调用工具和 skills 的助手。"
                    "仅当调用能力有助于回答用户问题时才调用。"
                    "需要多步调用时请通过多轮 tool call 推进。"
                    "如果你已经拿到足够信息，请直接给出最终自然语言回复。"
                    f"\n最近对话历史摘要:\n{history_summary}"
                ),
            },
            {"role": "user", "content": ctx.user_message},
        ]

        invocations: List[ToolInvocationTrace] = []
        rounds: List[LLMRoundTrace] = []
        plan_steps: List[ToolStep] = []
        final_text: Optional[str] = None
        max_rounds = 8

        for round_index in range(1, max_rounds + 1):
            req_snapshot = json.loads(json.dumps(messages, ensure_ascii=False))
            try:
                response = client.chat.completions.create(
                    model=self._config.model or "gpt-4.1-mini",
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0,
                )
            except Exception:
                return None, None, [], []

            msg = response.choices[0].message
            content = msg.content or ""
            tool_calls = getattr(msg, "tool_calls", None) or []

            if not tool_calls:
                final_text = content
                rounds.append(
                    LLMRoundTrace(
                        round_index=round_index,
                        request_messages=req_snapshot,
                        assistant_content=content,
                        tool_calls=[],
                        tool_results=[],
                    )
                )
                break

            assistant_tool_calls = []
            for tc in tool_calls:
                call_id = tc.id or f"call-{uuid.uuid4().hex[:8]}"
                assistant_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": assistant_tool_calls,
                }
            )

            import time as _time

            round_tool_calls: List[Dict[str, Any]] = []
            round_tool_results: List[Dict[str, Any]] = []
            for tc in tool_calls:
                call_id = tc.id or f"call-{uuid.uuid4().hex[:8]}"
                try:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    continue

                round_tool_calls.append(
                    {"tool_call_id": call_id, "name": name, "arguments": args}
                )
                step = ToolStep(capability_name=name, arguments=args)
                plan_steps.append(step)

                start = _time.perf_counter()
                status = "success"
                result_summary = ""
                tool_result: Dict[str, Any]
                try:
                    raw = self._capabilities.invoke(name, args)
                    if isinstance(raw, dict) and raw.get("error"):
                        status = "failed"
                    tool_result = {"ok": status == "success", "result": raw}
                    result_summary = str(raw)
                except Exception as exc:  # pragma: no cover
                    status = "failed"
                    tool_result = {"ok": False, "error": repr(exc)}
                    result_summary = tool_result["error"]
                end = _time.perf_counter()

                invocations.append(
                    ToolInvocationTrace(
                        step_id=step.step_id,
                        capability_name=name,
                        status=status,
                        latency_ms=(end - start) * 1000,
                        result_summary=result_summary,
                    )
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False),
                    }
                )
                round_tool_results.append(
                    {
                        "tool_call_id": call_id,
                        "name": name,
                        "status": status,
                        "result": tool_result,
                    }
                )

            rounds.append(
                LLMRoundTrace(
                    round_index=round_index,
                    request_messages=req_snapshot,
                    assistant_content=content,
                    tool_calls=round_tool_calls,
                    tool_results=round_tool_results,
                )
            )

        plan = ToolPlan(session_id=ctx.id, steps=plan_steps) if plan_steps else None
        if final_text is None and invocations:
            final_text = self._compose_tool_reply(invocations)
        return final_text, plan, invocations, rounds

    def _compose_tool_reply(self, invocations: List[ToolInvocationTrace]) -> str:
        by_name: Dict[str, ToolInvocationTrace] = {
            i.capability_name: i for i in invocations if i.status == "success"
        }
        failed = [i for i in invocations if i.status != "success"]

        if "time.now" in by_name:
            return f"当前时间（示例能力）: {by_name['time.now'].result_summary}"

        if "skill.error_count" in by_name or "skill.version_info" in by_name:
            parts: List[str] = []
            error_trace = by_name.get("skill.error_count")
            version_trace = by_name.get("skill.version_info")
            if error_trace:
                parts.append(f"今日错误数信息：{error_trace.result_summary}")
            if version_trace:
                parts.append(f"当前版本信息：{version_trace.result_summary}")
            if failed:
                missing = ", ".join(i.capability_name for i in failed)
                parts.append(f"部分信息暂缺（{missing} 调用失败）")
            if parts:
                parts.append("一句话总结：系统可用，但需关注错误数趋势。")
                return "；".join(parts)

        if invocations:
            last = invocations[-1]
            summary = last.result_summary
            if len(summary) > 200:
                summary = summary[:200] + "..."
            if last.status == "success":
                return f"工具 {last.capability_name} 调用成功，摘要：{summary}"
            return f"工具调用失败：{last.capability_name}，错误摘要：{summary}"

        return "工具调用完成，但结果不可用。"

    def run_with_trace(
        self,
        history: Iterable[Message],
        latest: Message,
        session_meta: SessionMeta | None = None,
    ) -> tuple[str, ExecutionTrace]:
        """根据历史与最新消息生成回复，并返回执行轨迹。"""

        meta = session_meta or SessionMeta(
            session_id=latest.conversation_id,
            channel="unknown",
            user_id="unknown",
            extra={},
        )
        ctx = self._build_context(history, latest, meta)

        llm_reply: Optional[str] = None
        plan: Optional[ToolPlan] = None
        invocations: List[ToolInvocationTrace] = []

        if self._config.api_key:
            llm_reply, plan, invocations, llm_rounds = self._run_llm_with_tool_loop(ctx)
            if llm_reply is None and plan is None:
                plan, llm_reply = self._decide_tool_plan(ctx)
                invocations = []
                llm_rounds = []
        else:
            plan, llm_reply = self._decide_tool_plan(ctx)
            llm_rounds = []

        if plan and plan.steps and not invocations:
            import time as _time

            status_by_step: Dict[str, str] = {}
            for step in plan.steps:
                if step.depends_on and any(
                    status_by_step.get(dep) != "success" for dep in step.depends_on
                ):
                    invocations.append(
                        ToolInvocationTrace(
                            step_id=step.step_id,
                            capability_name=step.capability_name,
                            status="skipped",
                            latency_ms=0.0,
                            result_summary="dependency not satisfied",
                        )
                    )
                    status_by_step[step.step_id] = "skipped"
                    continue

                start = _time.perf_counter()
                status = "success"
                result_summary = ""
                try:
                    result = self._capabilities.invoke(
                        step.capability_name, step.arguments
                    )
                    if isinstance(result, dict) and result.get("error"):
                        status = "failed"
                    result_summary = str(result)
                except Exception as exc:  # pragma: no cover
                    status = "failed"
                    result_summary = f"error: {exc!r}"
                end = _time.perf_counter()

                invocations.append(
                    ToolInvocationTrace(
                        step_id=step.step_id,
                        capability_name=step.capability_name,
                        status=status,
                        latency_ms=(end - start) * 1000,
                        result_summary=result_summary,
                    )
                )
                status_by_step[step.step_id] = status

            tool_reply = self._compose_tool_reply(invocations)
            reply_text = f"{llm_reply}\n\n{tool_reply}" if llm_reply else tool_reply
        elif plan and plan.steps and invocations:
            # LLM 工具循环已执行完成：优先使用 LLM 最终回复。
            if llm_reply:
                reply_text = llm_reply
            else:
                reply_text = self._compose_tool_reply(invocations)
        else:
            reply_text = llm_reply or f"[demo] 你刚才说：{latest.text}"

        trace = ExecutionTrace(
            session_id=meta.session_id,
            channel=meta.channel,
            user_message=latest.text,
            tool_plan=plan,
            tool_invocations=invocations,
            llm_rounds=llm_rounds,
            final_reply_summary=reply_text,
        )
        self._last_trace = trace
        return reply_text, trace

    def run(
        self,
        history: Iterable[Message],
        latest: Message,
        session_meta: SessionMeta | None = None,
    ) -> str:
        """向后兼容接口：仅返回回复文本。"""

        reply, _trace = self.run_with_trace(
            history=history, latest=latest, session_meta=session_meta
        )
        return reply
