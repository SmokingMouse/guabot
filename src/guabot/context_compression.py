from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Literal

if TYPE_CHECKING:
    from anthropic.types import MessageParam


MessageRole = Literal["user", "assistant", "system"]


@dataclass
class CompressionConfig:
    """上下文压缩配置"""

    enabled: bool = True
    trigger_threshold: float = 0.8  # 触发压缩的使用率阈值
    target_threshold: float = 0.6   # 压缩后的目标使用率
    keep_recent_turns: int = 5      # 保留最近 N 轮不压缩
    compression_model: str = "claude-haiku-4-5"  # 用于生成摘要的模型
    max_summary_tokens: int = 100   # 每对消息的最大摘要 tokens


@dataclass
class CompressionResult:
    """压缩结果"""

    compressed_messages: List[MessageParam]
    compressed_count: int
    original_token_count: int
    compressed_token_count: int
    compression_time: float


class ContextCompressor:
    """上下文压缩器"""

    def __init__(self, config: CompressionConfig):
        self.config = config

    def should_compress(
        self,
        current_tokens: int,
        context_limit: int
    ) -> bool:
        """检查是否需要压缩"""
        if not self.config.enabled:
            return False

        usage_ratio = current_tokens / context_limit if context_limit > 0 else 0
        return usage_ratio > self.config.trigger_threshold

    def compress_messages(
        self,
        messages: List[MessageParam],
        current_tokens: int,
        context_limit: int,
        llm_client: Any = None
    ) -> CompressionResult:
        """压缩消息列表

        Args:
            messages: 原始消息列表
            current_tokens: 当前 token 数
            context_limit: context 限制
            llm_client: LLM 客户端 (用于生成摘要)

        Returns:
            CompressionResult
        """
        start_time = time.time()

        # 分离 system 消息和对话消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        conversation_messages = [m for m in messages if m.get("role") != "system"]

        # 保留最近的 N 轮对话
        keep_recent = self.config.keep_recent_turns * 2  # user + assistant
        recent_messages = conversation_messages[-keep_recent:] if len(conversation_messages) > keep_recent else conversation_messages
        old_messages = conversation_messages[:-keep_recent] if len(conversation_messages) > keep_recent else []

        if not old_messages:
            # 没有可压缩的消息
            return CompressionResult(
                compressed_messages=messages,
                compressed_count=0,
                original_token_count=current_tokens,
                compressed_token_count=current_tokens,
                compression_time=time.time() - start_time
            )

        # 计算需要压缩多少消息才能达到目标
        target_tokens = int(context_limit * self.config.target_threshold)
        tokens_to_save = current_tokens - target_tokens

        # 简单策略: 压缩最旧的消息对,直到达到目标
        compressed_old = self._compress_old_messages(
            old_messages,
            tokens_to_save,
            llm_client
        )

        # 重新组合消息
        compressed_messages = system_messages + compressed_old + recent_messages

        # 估算压缩后的 token 数 (简化计算)
        compressed_token_count = self._estimate_tokens(compressed_messages)

        return CompressionResult(
            compressed_messages=compressed_messages,
            compressed_count=len(old_messages) - len(compressed_old),
            original_token_count=current_tokens,
            compressed_token_count=compressed_token_count,
            compression_time=time.time() - start_time
        )

    def _compress_old_messages(
        self,
        old_messages: List[MessageParam],
        tokens_to_save: int,
        llm_client: Any
    ) -> List[MessageParam]:
        """压缩旧消息

        策略: 将连续的 user/assistant 消息对合并为一条摘要消息
        """
        if not old_messages:
            return []

        # 将消息配对 (user + assistant)
        pairs: List[List[MessageParam]] = []
        current_pair: List[MessageParam] = []

        for msg in old_messages:
            current_pair.append(msg)
            if msg.get("role") == "assistant":
                pairs.append(current_pair)
                current_pair = []

        # 如果有剩余的未配对消息,也加入
        if current_pair:
            pairs.append(current_pair)

        # 如果没有 LLM 客户端,使用简单的截断策略
        if llm_client is None:
            return self._simple_truncate(pairs, tokens_to_save)

        # 使用 LLM 生成摘要 (TODO: 实现 LLM 调用)
        # 当前先使用简单策略
        return self._simple_truncate(pairs, tokens_to_save)

    def _simple_truncate(
        self,
        pairs: List[List[MessageParam]],
        tokens_to_save: int
    ) -> List[MessageParam]:
        """简单的截断策略: 用摘要替换最旧的消息对"""
        if not pairs:
            return []

        # 计算需要压缩多少对
        # 假设每对平均 200 tokens, 压缩后 50 tokens
        avg_tokens_per_pair = 200
        avg_compressed_tokens = 50
        tokens_saved_per_pair = avg_tokens_per_pair - avg_compressed_tokens

        pairs_to_compress = min(
            len(pairs) - 1,  # 至少保留一对
            max(1, tokens_to_save // tokens_saved_per_pair)
        )

        # 压缩最旧的 N 对
        compressed_pairs = pairs[:pairs_to_compress]
        remaining_pairs = pairs[pairs_to_compress:]

        # 生成摘要消息
        summary_content = self._generate_simple_summary(compressed_pairs)
        summary_message: MessageParam = {
            "role": "user",
            "content": f"[已压缩 {len(compressed_pairs)} 轮对话]\n{summary_content}"
        }

        # 重新组合
        result: List[MessageParam] = [summary_message]
        for pair in remaining_pairs:
            result.extend(pair)

        return result

    def _generate_simple_summary(self, pairs: List[List[MessageParam]]) -> str:
        """生成简单的摘要 (不调用 LLM)"""
        summaries = []
        for i, pair in enumerate(pairs, 1):
            user_msg = next((m for m in pair if m.get("role") == "user"), None)
            assistant_msg = next((m for m in pair if m.get("role") == "assistant"), None)

            user_preview = ""
            if user_msg:
                content = user_msg.get("content", "")
                if isinstance(content, str):
                    user_preview = content[:50] + "..." if len(content) > 50 else content

            assistant_preview = ""
            if assistant_msg:
                content = assistant_msg.get("content", "")
                if isinstance(content, str):
                    assistant_preview = content[:50] + "..." if len(content) > 50 else content

            summaries.append(f"轮次 {i}: {user_preview} → {assistant_preview}")

        return "\n".join(summaries)

    def _estimate_tokens(self, messages: List[MessageParam]) -> int:
        """估算消息的 token 数 (简化计算)"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                # 粗略估算: 1 token ≈ 4 字符
                total += len(content) // 4
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        total += len(block["text"]) // 4
        return total
