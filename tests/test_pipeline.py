from guabot.agent import AgentConfig, AgentExecutor
from guabot.capabilities import CapabilityRegistry, default_registry
from guabot.memory import Message, MemoryStore
from guabot.pipeline import IncomingMessage, build_default_pipeline, handle_incoming_message


def test_pipeline_echo_and_time_capability() -> None:
    pipeline = build_default_pipeline()

    incoming1 = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-1",
        user_id="u1",
        text="你好",
    )
    reply1 = handle_incoming_message(pipeline, incoming1)
    assert isinstance(reply1.text, str)
    assert reply1.text
    assert reply1.trace_id

    incoming2 = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-1",
        user_id="u1",
        text="现在时间是多少？",
    )
    reply2 = handle_incoming_message(pipeline, incoming2)
    assert "当前时间（示例能力）" in reply2.text


def test_agent_executor_produces_execution_trace() -> None:
    registry: CapabilityRegistry = default_registry()
    executor = AgentExecutor(AgentConfig(endpoint=None), registry)
    memory = MemoryStore(default_window_size=20)

    conv_id = "conv-trace-1"
    msg1 = Message(conversation_id=conv_id, sender="user", text="你好")
    memory.append(msg1)

    reply1, trace1 = executor.run_with_trace(history=list(memory.history(conv_id)), latest=msg1)
    assert "你刚才说" in reply1
    assert trace1.tool_plan is None
    assert trace1.tool_invocations == []

    msg2 = Message(conversation_id=conv_id, sender="user", text="现在时间是多少？")
    memory.append(msg2)
    reply2, trace2 = executor.run_with_trace(history=list(memory.history(conv_id)), latest=msg2)

    assert "当前时间（示例能力）" in reply2
    assert trace2.tool_plan is not None
    assert len(trace2.tool_plan.steps) == 1
    assert trace2.tool_plan.steps[0].capability_name == "time.now"
    assert len(trace2.tool_invocations) == 1
    assert trace2.tool_invocations[0].capability_name == "time.now"


def test_pipeline_multi_step_skills_success() -> None:
    pipeline = build_default_pipeline()

    incoming = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-skills-ok",
        user_id="u1",
        text="帮我查一下今天错误数和当前版本，并给个一句话总结",
    )
    reply = handle_incoming_message(pipeline, incoming)

    assert "错误数" in reply.text
    assert "版本" in reply.text
    assert "一句话总结" in reply.text

    trace = pipeline.trace_store.get(reply.trace_id or "")
    assert trace is not None
    assert trace.tool_plan is not None
    assert len(trace.tool_invocations) >= 2
    assert {x.capability_name for x in trace.tool_invocations} >= {"skill.error_count", "skill.version_info"}


def test_pipeline_multi_step_skills_partial_failure() -> None:
    pipeline = build_default_pipeline()

    incoming = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-skills-fail",
        user_id="u1",
        text="帮我查一下今天错误数和当前版本（版本不可用）并给个一句话总结",
    )
    reply = handle_incoming_message(pipeline, incoming)

    assert "错误数" in reply.text
    assert "部分信息暂缺" in reply.text

    trace = pipeline.trace_store.get(reply.trace_id or "")
    assert trace is not None
    assert any(x.capability_name == "skill.version_info" and x.status == "failed" for x in trace.tool_invocations)
