from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List


@dataclass
class Message:
    """标准化后的消息表示。

    为了保持极简，这里仅包含本特性所需的最小字段。
    """

    conversation_id: str
    sender: str  # "user" | "agent" | "system"
    text: str


class ConversationMemory:
    """维护单个会话最近 N 条消息的简单内存。"""

    def __init__(self, window_size: int) -> None:
        if window_size <= 0:
            raise ValueError("window_size MUST be positive")
        self._window_size = window_size
        self._messages: Deque[Message] = deque(maxlen=window_size)

    @property
    def window_size(self) -> int:
        return self._window_size

    def append(self, message: Message) -> None:
        self._messages.append(message)

    def history(self) -> List[Message]:
        """返回按时间顺序排序的历史消息副本。"""

        return list(self._messages)


class MemoryStore:
    """管理多会话记忆的简单内存存储。

    首版使用进程内存即可，后续可以在保持接口不变的前提下换成 Redis/数据库实现。
    """

    def __init__(self, default_window_size: int = 20) -> None:
        if default_window_size <= 0:
            raise ValueError("default_window_size MUST be positive")
        self._default_window_size = default_window_size
        self._conversations: Dict[str, ConversationMemory] = {}

    def get_or_create(self, conversation_id: str, window_size: int | None = None) -> ConversationMemory:
        if conversation_id not in self._conversations:
            self._conversations[conversation_id] = ConversationMemory(window_size or self._default_window_size)
        return self._conversations[conversation_id]

    def append(self, message: Message, window_size: int | None = None) -> None:
        memory = self.get_or_create(message.conversation_id, window_size)
        memory.append(message)

    def history(self, conversation_id: str) -> Iterable[Message]:
        memory = self._conversations.get(conversation_id)
        if not memory:
            return []
        return memory.history()

