from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Iterable, List


@dataclass
class Message:
    """标准化后的消息表示。"""

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
        return list(self._messages)


class MemoryStore:
    """管理多会话记忆的简单内存存储。"""

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


class ExecutionTraceStore:
    """执行轨迹内存存储，支持按 trace_id/session_id 查询。"""

    def __init__(self) -> None:
        self._by_id: Dict[str, Any] = {}
        self._by_session: Dict[str, Deque[str]] = defaultdict(lambda: deque(maxlen=100))

    def save(self, trace: Any) -> None:
        trace_id = getattr(trace, "id", None)
        session_id = getattr(trace, "session_id", None)
        if not trace_id or not session_id:
            return
        self._by_id[trace_id] = trace
        self._by_session[session_id].append(trace_id)

    def get(self, trace_id: str) -> Any | None:
        return self._by_id.get(trace_id)

    def list_by_session(self, session_id: str) -> List[Any]:
        ids = self._by_session.get(session_id, [])
        return [self._by_id[i] for i in ids if i in self._by_id]
