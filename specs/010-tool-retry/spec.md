# Feature Specification: Tool Retry & Fallback

**Feature Branch**: `010-tool-retry`
**Created**: 2026-02-28
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/tool_retry.py` - RetryStrategy, RetryConfig, RetryResult, execute_with_retry
- `src/guabot/config.py` - 添加 ToolRetryConfig 到 AppConfig
- `tests/test_tool_retry.py` - 单元测试 (13 个测试通过)

**Priority**: P0 (生产环境必需)

---

## 背景 & 问题

**问题**: Tool 调用可能因网络、API 限流、临时故障等原因失败,导致整个任务中断。

**目标**: 实现 tool 调用的自动重试和降级策略,提升系统健壮性。

---

## User Scenarios & Testing

### User Story 1 - 自动重试临时失败 (Priority: P0)

As a user, I want the agent to automatically retry failed tool calls (with backoff) so temporary failures don't break my task.

**Acceptance Scenarios**:

1. **Given** 一个 tool 调用因网络超时失败, **When** 重试 3 次后成功, **Then** 任务正常继续
2. **Given** 一个 tool 调用失败, **When** 查看 trace, **Then** 能看到重试次数和每次的错误
3. **Given** 重试 3 次后仍失败, **Then** agent 收到明确的失败信息,可以选择降级策略

---

### User Story 2 - 可配置的重试策略 (Priority: P1)

As a developer, I can configure retry behavior per tool (max retries, backoff, which errors to retry) so I can optimize for different failure modes.

**Acceptance Scenarios**:

1. **Given** tool A 配置为 max_retries=3, **When** 失败, **Then** 最多重试 3 次
2. **Given** tool B 配置为 no_retry, **When** 失败, **Then** 立即返回失败,不重试
3. **Given** 某个错误类型配置为 non_retryable, **When** 遇到该错误, **Then** 不重试

---

### User Story 3 - 降级策略 (Priority: P2)

As a user, I want the agent to try alternative approaches when a tool fails so the task can still complete.

**Acceptance Scenarios**:

1. **Given** skill A 失败且无法重试, **When** 存在 fallback skill B, **Then** 自动尝试 skill B
2. **Given** 所有 fallback 都失败, **Then** agent 向用户报告并请求指导

---

## Requirements

### Functional Requirements

- **FR-001**: 每个 tool 调用支持配置 max_retries (默认 3)
- **FR-002**: 重试使用指数退避: 1s, 2s, 4s, ...
- **FR-003**: 可配置哪些错误类型可重试 (network, timeout, rate_limit) vs 不可重试 (auth, invalid_input)
- **FR-004**: 重试信息记录到 trace,包括每次的错误和延迟
- **FR-005**: Tool 可声明 fallback_tools,失败时自动尝试
- **FR-006**: 超过 max_retries 后,返回明确的失败信息给 agent

### Non-Functional Requirements

- **NFR-001**: 重试逻辑不应阻塞其他操作
- **NFR-002**: 重试配置可在 guabot.toml 和 tool 定义中覆盖
- **NFR-003**: 总重试时间不应超过 30s (可配置)

---

## Architecture

### 配置参数

```toml
[tool_retry]
enabled = true
default_max_retries = 3
default_backoff_base = 1.0  # 秒
max_total_retry_time = 30.0  # 秒

# 可重试的错误类型
retryable_errors = ["NetworkError", "TimeoutError", "RateLimitError"]

# 不可重试的错误类型
non_retryable_errors = ["AuthenticationError", "InvalidInputError"]
```

### Tool 定义中的重试配置

```python
@capability(
    name="web.fetch",
    retry_config={
        "max_retries": 5,
        "backoff_base": 2.0,
        "fallback_tools": ["web.fetch_cached"]
    }
)
def fetch_url(url: str) -> str:
    ...
```

### 数据流

```
Tool 调用
  ↓
执行 → 失败?
  ↓
检查错误类型 → 可重试?
  ↓
检查重试次数 < max_retries?
  ↓
等待 backoff 时间
  ↓
重试 → 成功? → 返回结果
  ↓
失败 → 记录到 trace
  ↓
检查 fallback_tools?
  ↓
尝试 fallback → 成功? → 返回结果
  ↓
所有失败 → 返回失败信息
```

### 文件改动

```
src/guabot/
  tool_retry.py           # NEW: RetryStrategy, execute_with_retry()
  capabilities.py         # MODIFIED: 集成 retry 逻辑
  config.py               # MODIFIED: 添加 retry 配置
  tracing.py              # MODIFIED: 记录重试信息
```

---

## Success Criteria

- **SC-001**: 一个临时网络故障的 tool 调用能自动重试成功
- **SC-002**: 重试使用指数退避,trace 中能看到每次重试的延迟
- **SC-003**: 不可重试的错误立即失败,不浪费时间
- **SC-004**: Fallback tool 在主 tool 失败后自动执行
- **SC-005**: 总重试时间不超过配置的上限
