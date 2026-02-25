from __future__ import annotations

from guabot.pipeline import IncomingMessage, build_default_pipeline, handle_incoming_message


def main() -> None:
    """极简 CLI，用于在本地验证脚手架主流程。

    该入口模拟一条来自“demo”渠道的消息，并将 Agent 的回复打印到 stdout。
    实际接入主流 IM 时，只需在各自的 Webhook/回调处理函数中调用
    `handle_incoming_message` 即可。
    """

    pipeline = build_default_pipeline()
    incoming = IncomingMessage(
        channel_type="demo",
        conversation_id="demo-conv-1",
        user_id="demo-user",
        text="本地目录是啥样的",
    )
    outgoing = handle_incoming_message(pipeline, incoming)
    print(outgoing.text)


if __name__ == "__main__":
    main()
