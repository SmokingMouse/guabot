# Feature Specification: Task State Injection

**Feature Branch**: `007-task-state-injection`
**Created**: 2026-02-27
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/task_state.py` - TaskState, ActionEntry, TaskStateStore, extract/render functions
- `src/guabot/pipeline.py` - 集成 task_state_store
- `src/guabot/prompts.py` - 注入 task_state_block
- `tests/test_task_state.py` - 单元测试

**Input**: 解决多轮对话中 agent 上下文错位问题——agent 忘记已完成的步骤，重复执行早期操作。

---

## 背景 & 问题

**典型案例**：
1. 用户：查找 skill `claude-code` → agent 找到了，路径 `/path/A`
2. 用户：安装它 → agent 安装成功，目标 `~/.guabot/skills/claude-code`
3. 用户：把它移动到另一个目录 → agent **重新执行了查找**，而不是直接移动

**根本原因**：system prompt 中没有"当前任务状态"的显式表示。agent 每轮从 message 历史重新推断意图，早期的"查找"操作在历史中权重过高，新指令被错误关联。

**解决思路（轻量版）**：每轮结束后，从 trace 中提取已完成的操作，以 `<task_state>` 块注入下一轮的 system prompt。不引入额外 LLM 调用，纯规则提取。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent 不重复已完成的步骤 (Priority: P0)

As a user running a multi-step task, I want the agent to remember what it already did so it doesn't redo completed steps when I give the next instruction.

**Why this priority**: This is the core pain point — the case study above is a real regression.

**Independent Test**: Run a 3-step task (find → install → move); verify step 3 does not re-trigger step 1's tool calls.

**Acceptance Scenarios**:

1. **Given** the agent completed `skill.find` in turn 1, **When** I ask it to move the skill in turn 3, **Then** the agent does NOT call `skill.find` again.
2. **Given** the agent installed a skill in turn 2, **When** I ask about its location in turn 4, **Then** the agent answers from task state without calling `tool.shell` to re-discover it.

---

### User Story 2 - 任务状态在 system prompt 中可见 (Priority: P1)

As a developer debugging agent behavior, I want to see the injected task state in the trace so I can verify it's correct.

**Independent Test**: Check the trace JSON for a multi-step conversation; verify `system_prompt` contains a `<task_state>` block with the completed steps.

**Acceptance Scenarios**:

1. **Given** 2 tool calls completed in previous turns, **When** I inspect the trace for turn 3, **Then** `system_prompt` contains `<task_state>` listing those 2 actions.
2. **Given** a fresh conversation (turn 1), **Then** `<task_state>` is absent or empty — no noise for single-turn interactions.

---

### User Story 3 - 状态自动清理 (Priority: P2)

As a user starting a new unrelated task in the same conversation, I don't want stale task state from a previous task to confuse the agent.

**Independent Test**: Complete a 3-step task, then ask a completely unrelated question; verify the agent doesn't reference the old task state in its reasoning.

**Acceptance Scenarios**:

1. **Given** task state has 5+ completed steps, **When** the user sends a message with no relation to the previous task, **Then** the agent responds correctly without being confused by old state.
2. **Given** the conversation has been idle for a configurable TTL, **Then** task state is cleared on the next turn.

---

### Edge Cases

- Tool call fails mid-task: failed steps should NOT appear in completed list; they should appear as `<failed>` so agent knows to retry or report.
- Very long task (20+ steps): task state block should cap at last N steps to avoid bloating the system prompt.
- Concurrent conversations: task state is per `conversation_id`, no cross-contamination.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: After each turn, the pipeline MUST extract completed tool invocations from the trace and store them per `conversation_id`.
- **FR-002**: On the next turn, the pipeline MUST inject a `<task_state>` block into the system prompt containing the last N completed actions (default N=10).
- **FR-003**: Failed tool invocations MUST be recorded as `<failed>` entries, not `<completed>`.
- **FR-004**: Task state MUST be cleared when the conversation has been idle for longer than `task_state_ttl` (configurable, default 30 min).
- **FR-005**: If there are no completed actions yet (turn 1), the `<task_state>` block MUST be omitted entirely.
- **FR-006**: Each action entry MUST include: tool name, key argument (first non-trivial arg), and outcome summary (≤80 chars).

### Non-Functional Requirements

- **NFR-001**: Task state extraction MUST add < 5ms to pipeline latency (no LLM call).
- **NFR-002**: Task state storage MUST be in-memory only (no disk write) — it's ephemeral session data.
- **NFR-003**: The `<task_state>` block MUST be ≤ 500 tokens to avoid bloating the context window.

### Key Entities

- **TaskState**: Per-conversation state object — list of `ActionEntry` + last-updated timestamp.
- **ActionEntry**: `{ tool: str, summary: str, status: "completed" | "failed", turn: int }`.
- **TaskStateStore**: In-memory dict `conversation_id → TaskState`. Lives in `PipelineContext`.
- **extract_action_entries(trace)**: Pure function — takes `ExecutionTrace`, returns list of `ActionEntry`.
- **render_task_state_block(state)**: Pure function — returns XML string or `""` if empty.

---

## Architecture

### 数据流

```
Turn N ends
  └─ extract_action_entries(trace) → List[ActionEntry]
       └─ TaskStateStore.update(conversation_id, entries)

Turn N+1 starts
  └─ render_task_state_block(state) → XML string
       └─ injected into system prompt as <task_state> block
```

### 文件改动

```
src/guabot/
  task_state.py          # NEW: TaskState, ActionEntry, TaskStateStore,
                         #      extract_action_entries(), render_task_state_block()
  pipeline.py            # MODIFIED: add task_state_store to PipelineContext,
                         #           call extract + update after run_with_trace,
                         #           pass state to render_system_prompt
  prompts.py             # MODIFIED: render_system_prompt() accepts task_state param,
                         #           injects <task_state> block into SYSTEM_PROMPT_TEMPLATE
```

### System Prompt 注入位置

在 `<behavior>` 块之后、`{profile_block}` 之前插入：

```xml
<task_state>
  <completed>
    <action turn="1" tool="skill.find">找到 claude-code → /path/to/skill</action>
    <action turn="2" tool="skill.run">安装 claude-code → ~/.guabot/skills/claude-code</action>
  </completed>
</task_state>
```

失败示例：

```xml
<task_state>
  <completed>
    <action turn="1" tool="skill.find">找到 claude-code → /path/to/skill</action>
  </completed>
  <failed>
    <action turn="2" tool="skill.run">安装失败：permission denied</action>
  </failed>
</task_state>
```

### extract_action_entries 逻辑

```python
def extract_action_entries(trace: ExecutionTrace, turn: int) -> list[ActionEntry]:
    entries = []
    for inv in trace.tool_invocations:
        summary = _summarize(inv)   # tool name + first key arg + result snippet
        status = "completed" if inv.status == "success" else "failed"
        entries.append(ActionEntry(tool=inv.tool_name, summary=summary, status=status, turn=turn))
    return entries
```

`_summarize` 规则（纯字符串操作，无 LLM）：
- 取 `inv.tool_name` + args 中第一个非空字符串值（截断到 40 chars）
- 取 `inv.result` 的前 40 chars（去掉换行）
- 格式：`"{key_arg} → {result_snippet}"`

---

## Assumptions

- `ExecutionTrace.tool_invocations` 已包含 `tool_name`, `status`, `args`, `result` 字段（当前代码已有）。
- Task state 是 session 级别的，不持久化到磁盘——重启后清空是可接受的。
- `task_state_ttl` 默认 30 分钟，可在 `guabot.toml` 中配置。

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The case study (find → install → move) passes without agent re-doing the find step.
- **SC-002**: Turn 1 system prompt contains NO `<task_state>` block.
- **SC-003**: Turn 3 system prompt contains `<task_state>` with 2 completed actions from turns 1-2.
- **SC-004**: A failed tool call appears in `<failed>`, not `<completed>`.
- **SC-005**: Task state extraction adds < 5ms measured in unit tests.
- **SC-006**: After TTL expiry, the next turn's system prompt has no `<task_state>` block.
