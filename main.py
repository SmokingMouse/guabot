from __future__ import annotations

import json

from guabot.pipeline import (
    IncomingMessage,
    build_default_pipeline,
    handle_incoming_message,
)


def _build_message_timeline(trace) -> list[dict]:
    """将多轮轨迹合并为一条无重复的 messages 时间线。"""

    rounds = list(getattr(trace, "llm_rounds", []) or [])
    if not rounds:
        return []

    timeline = list(rounds[0].request_messages)
    for round_trace in rounds[1:]:
        snapshot = list(round_trace.request_messages)
        if len(snapshot) >= len(timeline) and snapshot[: len(timeline)] == timeline:
            timeline.extend(snapshot[len(timeline) :])
        else:
            timeline = snapshot

    last_round = rounds[-1]
    if last_round.tool_calls:
        timeline.append(
            {
                "role": "assistant",
                "content": last_round.assistant_content,
                "tool_calls": last_round.tool_calls,
            }
        )
        for result in last_round.tool_results:
            timeline.append(
                {
                    "role": "tool",
                    "tool_call_id": result.get("tool_call_id"),
                    "name": result.get("name"),
                    "content": json.dumps(result.get("result", {}), ensure_ascii=False),
                }
            )
    elif last_round.assistant_content:
        timeline.append({"role": "assistant", "content": last_round.assistant_content})

    return timeline


def main() -> None:
    """交互式 CLI：循环提问并输出 Agent 整理后的回答。"""

    pipeline = build_default_pipeline()
    conversation_id = "demo-conv-1"
    user_id = "demo-user"

    print("Guabot 已启动，输入问题后回车即可提问；输入 /exit 退出。")
    while True:
        try:
            user_text = input("你> ").strip()
        except EOFError:
            print("\n已退出。")
            break

        if not user_text:
            continue
        if user_text in {"/exit", "/quit"}:
            print("已退出。")
            break

        incoming = IncomingMessage(
            channel_type="demo",
            conversation_id=conversation_id,
            user_id=user_id,
            text=user_text,
        )
        outgoing = handle_incoming_message(pipeline, incoming)
        print("----- 过程信息 -----")
        print(f"用户问题: {user_text}")
        if outgoing.trace_id:
            print(f"trace_id: {outgoing.trace_id}")
            trace = pipeline.trace_store.get(outgoing.trace_id)
            if trace is not None:
                if trace.llm_rounds:
                    print("LLM交互messages(完整时间线):")
                    timeline = _build_message_timeline(trace)
                    print(
                        "  "
                        + json.dumps(timeline, ensure_ascii=False, indent=2).replace(
                            "\n", "\n  "
                        )
                    )
                else:
                    print("LLM交互: 当前为本地规则兜底，未记录在线模型轮次。")

                if trace.tool_plan and trace.tool_plan.steps:
                    print("计划步骤:")
                    for idx, step in enumerate(trace.tool_plan.steps, start=1):
                        print(
                            f"  {idx}. {step.capability_name} args={step.arguments}"
                        )
                else:
                    print("计划步骤: 无（直接回复）")

                if trace.tool_invocations:
                    print("工具执行:")
                    for idx, inv in enumerate(trace.tool_invocations, start=1):
                        summary = inv.result_summary
                        if len(summary) > 160:
                            summary = summary[:160] + "..."
                        print(
                            f"  {idx}. {inv.capability_name} | {inv.status} | "
                            f"{inv.latency_ms:.2f}ms | {summary}"
                        )
                else:
                    print("工具执行: 无")
        print("----- 最终回复 -----")
        print(f"助手> {outgoing.text}")
        print("-------------------")


if __name__ == "__main__":
    main()
