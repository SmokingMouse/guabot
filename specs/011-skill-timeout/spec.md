# Feature Specification: Skill Timeout Handling

**Feature Branch**: `011-skill-timeout`
**Created**: 2026-02-28
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/skill_timeout.py` - TimeoutManager, TimeoutConfig, TimeoutResult
- `src/guabot/config.py` - 添加 SkillTimeoutConfig 到 AppConfig
- `tests/test_skill_timeout.py` - 单元测试 (8 个测试通过)

**Priority**: P0 (防止 hang 住)

---

## 背景 & 问题

**问题**: Skill 执行可能因为死循环、阻塞 I/O、外部服务无响应等原因 hang 住,导致整个 agent 卡死。

**目标**: 为每个 skill 执行设置超时限制,超时后自动终止并返回错误。

---

## User Scenarios & Testing

### User Story 1 - 自动超时终止 (Priority: P0)

As a user, I want skills to automatically timeout if they run too long so my agent doesn't hang forever.

**Acceptance Scenarios**:

1. **Given** 一个 skill 配置了 30s 超时, **When** 执行超过 30s, **Then** 自动终止并返回超时错误
2. **Given** skill 超时, **When** 查看 trace, **Then** 能看到超时信息和执行时长
3. **Given** skill 超时, **When** agent 收到错误, **Then** 可以选择重试或换策略

---

### User Story 2 - 可配置的超时时间 (Priority: P1)

As a developer, I can configure timeout per skill (some need 5s, some need 5min) so I can balance responsiveness and task completion.

**Acceptance Scenarios**:

1. **Given** skill A 配置为 timeout=10s, **When** 执行, **Then** 10s 后超时
2. **Given** skill B 配置为 timeout=300s, **When** 执行, **Then** 300s 后超时
3. **Given** skill C 未配置 timeout, **When** 执行, **Then** 使用默认超时 (60s)

---

### User Story 3 - 优雅终止 (Priority: P2)

As a developer, I want skills to receive a cancellation signal before being killed so they can clean up resources.

**Acceptance Scenarios**:

1. **Given** skill 支持 cancellation, **When** 超时触发, **Then** 先发送 cancel 信号,等待 5s 后再强制终止
2. **Given** skill 在 cancel 信号后完成清理, **When** 返回, **Then** trace 标记为 "cancelled" 而非 "timeout"

---

## Requirements

### Functional Requirements

- **FR-001**: 每个 skill 执行使用 asyncio.timeout 或 threading.Timer 限制执行时间
- **FR-002**: 默认超时时间 60s,可在 guabot.toml 和 skill 定义中覆盖
- **FR-003**: 超时后,记录详细信息到 trace: 执行时长、超时阈值、当前状态
- **FR-004**: 超时错误返回给 agent,包含建议 (如 "可能需要更长超时" 或 "检查外部服务")
- **FR-005**: 支持 skill 声明 cancellable=True,超时时先发送 cancel 信号
- **FR-006**: 强制终止前等待 grace_period (默认 5s) 让 skill 清理

### Non-Functional Requirements

- **NFR-001**: 超时检测精度 ±1s (不需要毫秒级)
- **NFR-002**: 超时终止不应影响其他并发 skill 执行
- **NFR-003**: 超时配置可在运行时动态调整 (通过 config reload)

---

## Architecture

### 配置参数

```toml
[skill_timeout]
enabled = true
default_timeout = 60.0  # 秒
grace_period = 5.0      # 优雅终止等待时间

# 特定 skill 的超时覆盖
[skill_timeout.overrides]
"web.scrape" = 300.0    # 爬虫需要更长时间
"math.calculate" = 5.0  # 计算应该很快
```

### Skill 定义中的超时配置

```python
@skill(
    name="long_running_task",
    timeout=300.0,
    cancellable=True
)
async def long_task(ctx: SkillContext) -> str:
    # 检查 cancellation
    if ctx.is_cancelled():
        # 清理资源
        return "cancelled"
    ...
```

### 数据流

```
Skill 执行开始
  ↓
启动 timeout timer
  ↓
执行 skill 逻辑
  ↓
完成? → 取消 timer → 返回结果
  ↓
超时触发?
  ↓
Cancellable? → 发送 cancel 信号
  ↓
等待 grace_period
  ↓
仍未完成? → 强制终止
  ↓
记录超时到 trace
  ↓
返回超时错误
```

### 文件改动

```
src/guabot/
  skill_timeout.py        # NEW: TimeoutManager, execute_with_timeout()
  skills/                 # MODIFIED: skill 执行集成 timeout
  config.py               # MODIFIED: 添加 timeout 配置
  tracing.py              # MODIFIED: 记录超时信息
```

---

## Success Criteria

- **SC-001**: 一个 sleep(100) 的 skill 在 60s 后自动超时
- **SC-002**: 超时信息记录到 trace,包含执行时长
- **SC-003**: Cancellable skill 收到 cancel 信号后能优雅终止
- **SC-004**: 超时不影响其他并发 skill 的执行
- **SC-005**: 配置的超时时间能正确生效
