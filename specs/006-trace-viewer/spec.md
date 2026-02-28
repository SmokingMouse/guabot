# Feature Specification: Conversation Trace Viewer

**Feature Branch**: `006-trace-viewer`
**Created**: 2026-02-27
**Status**: 🟡 Partial (Backend ✅, Frontend ⏳)
**Implementation**:
- ✅ `src/guabot/tracing.py` - ExecutionTrace, 自动写 trace JSON
- ✅ `tests/test_tracing.py` - 单元测试
- ⏳ Next.js viewer - 待实现

**Input**: 为优化 prompt 和 memory 机制，需要追溯每次对话的完整执行过程：调用了哪些工具、具体的 message、失效的 message 等。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 查看对话执行详情 (Priority: P1)

As a developer, I can open the trace viewer and see a specific conversation's full execution — every turn, tool call, and message status — so I can understand what the agent actually did.

**Why this priority**: 这是核心价值，没有这个其他功能都没意义。

**Independent Test**: 跑一次包含工具调用的对话，打开 viewer，能看到每个 turn 的 user message、tool calls（含 input/output）、assistant reply。

**Acceptance Scenarios**:

1. **Given** 一次对话已完成，**When** 在 viewer 中打开该对话，**Then** 能看到每个 turn 的完整信息：user message、tool calls（名称/状态/耗时）、assistant reply。
2. **Given** 某个 turn 中有工具调用失败，**When** 查看该 turn，**Then** 失败的 tool call 有明显的视觉区分（颜色/图标），并能展开查看 error 详情。
3. **Given** tool call 有 input/output，**When** 默认展示时，**Then** input/output 默认折叠，点击可展开。

---

### User Story 2 - 查看 message 生命周期 (Priority: P1)

As a developer, I can see which messages were active, compressed, or expired at each turn so I can understand where context was lost.

**Why this priority**: 这是优化 memory 机制的直接依据。

**Independent Test**: 跑一次超过 context 压缩阈值的长对话，在 viewer 中能看到哪个 turn 触发了压缩，哪些 message 被标记为 compressed。

**Acceptance Scenarios**:

1. **Given** 对话中发生了 context 压缩，**When** 查看对应 turn，**Then** 有明显标记（如 "⚠ context compressed: turns 1-3 已压缩"）。
2. **Given** 某条 message 状态为 expired 或 failed，**When** 查看该 turn，**Then** 该 message 有视觉区分。

---

### User Story 3 - 查看 API 层 message 编排 (Priority: P1)

As a developer, I can inspect the exact LLM API messages (system/history/user/assistant/tool) per round so I can debug prompt composition and context loss accurately.

**Why this priority**: 仅看 turn 级摘要不足以定位 prompt/memory 问题，必须看到真实请求给模型的 message 序列。

**Independent Test**: 跑一次包含工具调用的对话，在 viewer 中打开某个 turn，能看到该 turn 的 `llm_rounds.request_messages` 原始顺序，以及 assistant tool_calls 与 tool 结果消息的对应关系。

**Acceptance Scenarios**:

1. **Given** 某 turn 含多轮 LLM 调用，**When** 打开该 turn 的 API Messages 面板，**Then** 能按 round 切换查看每轮 `request_messages`，并保留原始顺序。
2. **Given** 某轮 assistant 发起了 tool_calls，**When** 查看该轮消息，**Then** 能看到 assistant(tool_calls) 与 tool(role=tool, tool_call_id=...) 的一一对应。
3. **Given** 某条 message 被压缩或失效，**When** 查看 API messages，**Then** 该 message 在列表中有生命周期标记（active/compressed/expired/failed）。

---

### User Story 4 - 浏览所有对话 (Priority: P2)

As a developer, I can see a list of all recorded conversations with summary stats so I can quickly find the one I want to analyze.

**Independent Test**: 跑多次对话后，打开 viewer 首页，能看到对话列表，按时间倒序，每条显示 channel、turns 数、tool 错误数。

**Acceptance Scenarios**:

1. **Given** 有多条 trace 文件，**When** 打开 viewer 首页，**Then** 列出所有对话，显示：时间、channel、turns 数、tool 错误数。
2. **Given** 对话列表，**When** 点击某条，**Then** 跳转到该对话详情页。

---

### Edge Cases

- trace 文件损坏或格式不合法时，viewer 显示错误提示而不是崩溃。
- 对话中没有任何工具调用时，正常展示纯文本对话。
- `traces/data/` 目录为空时，首页显示空状态提示。
- 某轮 `request_messages` 超长（如工具结果 > 4KB）时，trace 可截断并标注 `truncated=true`，viewer 可见截断提示。

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Agent 执行过程中 MUST 自动将 trace 数据写入 `traces/data/<timestamp>_<id>.json`，无需手动触发。
- **FR-002**: 每个 trace 文件 MUST 包含：对话元信息、每个 turn 的 user message、assistant reply、tool calls（含 input/output/status/duration）、message 状态。
- **FR-003**: Viewer MUST 通过 Next.js API route 读取本地 `traces/data/` 目录下的 JSON 文件，不需要用户手动选择文件。
- **FR-004**: Viewer 首页 MUST 展示对话列表，按 started_at 倒序，每条显示 channel、turn 数、tool 错误数。
- **FR-005**: 对话详情页 MUST 按 turn 顺序展示，每个 turn 包含 user message、tool calls、assistant reply。
- **FR-006**: Tool call 的 input/output MUST 默认折叠，点击展开。
- **FR-007**: 失败的 tool call MUST 有视觉区分（红色/错误图标）。
- **FR-008**: Context 压缩事件 MUST 在对应 turn 处有明显标记。
- **FR-009**: 每个 turn MUST 记录 `llm_rounds`，至少包含 `round_index`、`request_messages`、`assistant_content`、`tool_calls`、`tool_results`。
- **FR-010**: `request_messages` MUST 保留发往 LLM API 的原始顺序与 role（`system`/`user`/`assistant`/`tool`）。
- **FR-011**: Viewer 详情页 MUST 提供 API Messages 视图，支持按 round 查看消息，并显示 `tool_call_id` 关联链路。
- **FR-012**: 对于超长 message 内容，trace 写入层 MUST 允许截断并保留截断标记（如 `truncated: true`），避免 trace 文件无限膨胀。
- **FR-013**: API Messages 视图 MUST 显示每条 message 的生命周期状态（active/compressed/expired/failed；未知时为 null/未标注）。

### Key Entities

- **Trace**: 一次完整对话的记录，包含元信息和所有 turns。
- **Turn**: 对话中的一轮交互，包含 user message、tool calls、assistant reply、message 状态。
- **ToolCall**: 单次工具调用记录，包含 tool_name、input、output、duration_ms、status。
- **MessageStatus**: 当前 turn 时的 message 生命周期状态（active / compressed / expired / failed）。
- **LLMRound**: 单个 turn 内的一次 LLM 请求/响应轮次，包含该轮请求消息快照与工具调用结果。
- **APIMessage**: 实际发送到模型 API 的 message 项，最少包含 role/content，可选 `tool_call_id`、`tool_calls`、`name`、`truncated`、`lifecycle_status`。

---

## Data Model

### Trace JSON Schema

```json
{
  "id": "abc123",
  "channel": "telegram",
  "started_at": "2026-02-27T10:30:00Z",
  "ended_at": "2026-02-27T10:45:00Z",
  "turns": [
    {
      "turn_id": 1,
      "timestamp": "2026-02-27T10:30:01Z",
      "user_message": { "content": "...", "token_count": 12 },
      "tool_calls": [
        {
          "tool_name": "read_file",
          "input": { "path": "..." },
          "output": "...",
          "duration_ms": 120,
          "status": "success"
        }
      ],
      "assistant_reply": { "content": "...", "token_count": 45 },
      "llm_rounds": [
        {
          "round_index": 1,
          "request_messages": [
            {
              "role": "system",
              "content": "<system_prompt>...</system_prompt>",
              "lifecycle_status": "active"
            },
            {
              "role": "user",
              "content": "请读取 README 并总结",
              "lifecycle_status": "active"
            }
          ],
          "assistant_content": "",
          "tool_calls": [
            {
              "tool_call_id": "call_1",
              "name": "read_file",
              "arguments": { "path": "README.md" }
            }
          ],
          "tool_results": [
            {
              "tool_call_id": "call_1",
              "name": "read_file",
              "status": "success",
              "result": { "content": "..." }
            }
          ]
        },
        {
          "round_index": 2,
          "request_messages": [
            {
              "role": "assistant",
              "content": "",
              "tool_calls": [
                {
                  "id": "call_1",
                  "type": "function",
                  "function": {
                    "name": "read_file",
                    "arguments": "{\"path\":\"README.md\"}"
                  }
                }
              ],
              "lifecycle_status": "active"
            },
            {
              "role": "tool",
              "tool_call_id": "call_1",
              "name": "read_file",
              "content": "{\"content\":\"...\"}",
              "truncated": false,
              "lifecycle_status": "active"
            }
          ],
          "assistant_content": "README 总结如下...",
          "tool_calls": [],
          "tool_results": []
        }
      ],
      "message_status": "active",
      "context_event": null
    }
  ]
}
```

`message_status`: `active` | `compressed` | `expired` | `failed`
`tool_call.status`: `success` | `error` | `denied`
`context_event.type`: `compressed` | `null`
`request_messages[].role`: `system` | `user` | `assistant` | `tool`
`request_messages[].lifecycle_status`: `active` | `compressed` | `expired` | `failed` | `null`

---

## Technical Architecture

```
guabot/
  traces/
    viewer/                      ← Next.js app (React + Tailwind)
      src/app/
        page.tsx                 ← 对话列表
        [id]/page.tsx            ← 对话详情
      src/app/api/
        traces/route.ts          ← 列出所有 trace 文件
        traces/[id]/route.ts     ← 读取单个 trace 文件
    data/
      2026-02-27_10-30_abc123.json

  src/guabot/
    tracing.py                   ← Trace 写入逻辑（turn 摘要 + llm_rounds）
    pipeline.py                  ← 将 execution trace 的 llm_rounds 传给 tracing

  main.py
    _build_message_timeline()    ← 参考实现：从 llm_rounds 构建 message 时间线
```

Next.js API routes 通过 Node.js `fs` 读取 `../data/` 目录，无需数据库，无需用户操作。

---

## Assumptions

- Viewer 作为本地开发工具运行（`npm run dev`），不需要部署。
- Trace 文件只写不改，对话结束后 JSON 文件即为最终状态。
- 初始版本不需要搜索或过滤，列表按时间倒序足够。
- Token count 如果 agent 不提供则为 null，viewer 不强依赖。

---

## Success Criteria *(mandatory)*

- **SC-001**: 每次对话结束后，`traces/data/` 下自动生成对应 JSON 文件，无遗漏。
- **SC-002**: Viewer 首页能在 1 秒内列出所有 trace 文件。
- **SC-003**: 对话详情页完整展示所有 turns 和 tool calls，无数据丢失。
- **SC-004**: 失败的 tool call 和 context 压缩事件在 UI 上有明显视觉区分，无需阅读原始 JSON 即可识别问题。
- **SC-005**: 至少 1 个包含工具调用的 turn 在详情页可展示 `llm_rounds.request_messages`，并能正确对应 `tool_call_id` 链路。
- **SC-006**: 对于被截断的 API message，UI 明确显示“内容已截断”，且不影响其他 messages 正常渲染。
