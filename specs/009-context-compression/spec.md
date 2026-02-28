# Feature Specification: Context Compression

**Feature Branch**: `009-context-compression`
**Created**: 2026-02-28
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/context_compression.py` - ContextCompressor, CompressionConfig, CompressionResult
- `src/guabot/config.py` - 添加 ContextCompressionConfig 到 AppConfig
- `src/guabot/pipeline.py` - 集成 context_compressor 到 PipelineContext
- `tests/test_context_compression.py` - 单元测试 (7 个测试全部通过)

**Priority**: P0 (长对话必需)

---

## 背景 & 问题

**问题**: 当对话超过 context window 限制时,guabot 会失败或行为异常。

**目标**: 实现滑动窗口压缩策略,在接近 context limit 时自动压缩旧消息,保持对话可持续进行。

---

## User Scenarios & Testing

### User Story 1 - 自动触发压缩 (Priority: P0)

As a user having a long conversation, I want the agent to automatically compress old messages when approaching context limit so the conversation doesn't fail.

**Acceptance Scenarios**:

1. **Given** context 使用率超过 80%, **When** 下一轮对话开始, **Then** 自动压缩最旧的 N 条消息
2. **Given** 压缩后的消息, **When** agent 需要引用历史, **Then** 能看到压缩摘要而不是完整内容
3. **Given** 压缩触发, **When** 查看 trace, **Then** 能看到哪些消息被压缩了

---

### User Story 2 - 保留关键信息 (Priority: P1)

As a user, I want important context (like task goals, user preferences) to be preserved even when compression happens.

**Acceptance Scenarios**:

1. **Given** 用户在对话开始时设定了目标, **When** 压缩发生, **Then** 目标信息不被压缩
2. **Given** 某条消息被标记为 "pin", **When** 压缩发生, **Then** 该消息保持完整

---

## Requirements

### Functional Requirements

- **FR-001**: 在每轮对话前,检查 context 使用率 (input_tokens / context_limit)
- **FR-002**: 当使用率 > 80% 时,触发压缩策略
- **FR-003**: 压缩策略: 将最旧的 N 条 user/assistant 消息对替换为摘要
- **FR-004**: 摘要生成: 调用 LLM 生成简短摘要 (≤100 tokens per message pair)
- **FR-005**: System prompt 和最近 M 条消息不参与压缩 (M 可配置,默认 5)
- **FR-006**: 压缩后的消息在 trace 中标记为 "compressed"

### Non-Functional Requirements

- **NFR-001**: 压缩操作应在 < 2s 内完成 (使用 haiku 等快速模型)
- **NFR-002**: 压缩后的 context 使用率应降至 < 60%
- **NFR-003**: 压缩配置可在 guabot.toml 中调整

---

## Architecture

### 配置参数

```toml
[context_compression]
enabled = true
trigger_threshold = 0.8  # 触发压缩的使用率阈值
target_threshold = 0.6   # 压缩后的目标使用率
keep_recent_turns = 5    # 保留最近 N 轮不压缩
compression_model = "claude-haiku-4-5"  # 用于生成摘要的模型
```

### 数据流

```
Turn N+1 开始
  ↓
检查 context 使用率
  ↓
> 80%? → 触发压缩
  ↓
选择要压缩的消息 (最旧的,排除 system/recent/pinned)
  ↓
调用 LLM 生成摘要
  ↓
替换原消息为摘要消息
  ↓
更新 trace 标记
  ↓
继续正常流程
```

### 文件改动

```
src/guabot/
  context_compression.py  # NEW: CompressionStrategy, compress_messages()
  pipeline.py             # MODIFIED: 在 run_turn 前检查并压缩
  config.py               # MODIFIED: 添加 compression 配置
  tracing.py              # MODIFIED: 添加 compressed 状态标记
```

---

## Success Criteria

- **SC-001**: 一个 50 轮的长对话能够正常完成,不会因 context limit 失败
- **SC-002**: 压缩触发时,context 使用率从 > 80% 降至 < 60%
- **SC-003**: 压缩操作耗时 < 2s
- **SC-004**: Trace 中能看到哪些消息被压缩了
