from guabot.agent import AgentConfig, AgentExecutor
from guabot.capabilities import CapabilityRegistry, default_registry
from guabot.memory import Message, MemoryStore
from guabot.pipeline import IncomingMessage, PipelineContext, build_default_pipeline, handle_incoming_message


def test_pipeline_echo_and_time_capability() -> None:
    pipeline = build_default_pipeline()

    # 第一次发送普通文本，应走 echo 分支
    incoming1 = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-1",
        user_id="u1",
        text="你好",
    )
    reply1 = handle_incoming_message(pipeline, incoming1)
    # 无论是否配置 LLM，只要能返回非空文本即可；具体内容由 LLM 或占位逻辑决定。
    assert isinstance(reply1.text, str)
    assert reply1.text

    # 第二次发送包含“时间”的文本，应触发 time.now 能力
    incoming2 = IncomingMessage(
        channel_type="demo",
        conversation_id="conv-1",
        user_id="u1",
        text="现在时间是多少？",
    )
    reply2 = handle_incoming_message(pipeline, incoming2)
    assert "当前时间（示例能力）" in reply2.text


def test_agent_executor_produces_execution_trace() -> None:
    """验证 AgentExecutor 在决策调用工具时会生成 ExecutionTrace。"""

    registry: CapabilityRegistry = default_registry()
    executor = AgentExecutor(AgentConfig(endpoint=None), registry)
    memory = MemoryStore(default_window_size=20)

    conv_id = "conv-trace-1"
    msg1 = Message(conversation_id=conv_id, sender="user", text="你好")
    memory.append(msg1)

    # 第一次：不触发工具调用
    reply1, trace1 = executor.run_with_trace(history=list(memory.history(conv_id)), latest=msg1)
    assert "你刚才说" in reply1
    assert trace1.tool_plan is None
    assert trace1.tool_invocations == []

    # 第二次：触发 time.now 工具调用
    msg2 = Message(conversation_id=conv_id, sender="user", text="现在时间是多少？")
    memory.append(msg2)
    reply2, trace2 = executor.run_with_trace(history=list(memory.history(conv_id)), latest=msg2)

    assert "当前时间（示例能力）" in reply2
    assert trace2.tool_plan is not None
    assert len(trace2.tool_plan.steps) == 1
    assert trace2.tool_plan.steps[0].capability_name == "time.now"
    assert len(trace2.tool_invocations) == 1
    assert trace2.tool_invocations[0].capability_name == "time.now"
