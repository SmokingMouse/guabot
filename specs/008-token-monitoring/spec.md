# Feature Specification: Token Monitoring

**Feature Branch**: `008-token-monitoring`
**Created**: 2026-02-28
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/token_stats.py` - TokenStats, TokenStatsCollector, 费用估算
- `tests/test_token_stats.py` - 单元测试
- 集成到 `pipeline.py` 和 `cli/shell.py`

**Priority**: P1（成本可见性，调优基础）

---

## User Scenarios & Testing

### User Story 1 - 查看单次对话的 token 消耗 (Priority: P1)

As a developer, I can see the token usage (input/output/total) for each conversation turn so I can understand the cost of each interaction.

**Acceptance Scenarios**:

1. **Given** 一次对话已完成，**When** 查看 trace viewer 详情页，**Then** 每个 turn 显示 input_tokens、output_tokens、total_tokens。
2. **Given** 某个 turn 包含多轮 LLM 调用，**When** 查看该 turn，**Then** 能看到每轮的 token 消耗和总计。

---

### User Story 2 - 按 tool/skill 分类的 token 消耗 (Priority: P2)

As a developer, I can see token usage grouped by tool/skill so I can identify which capabilities are most expensive.

**Acceptance Scenarios**:

1. **Given** 多次对话已完成，**When** 查看 token 统计页面，**Then** 能看到按 tool/skill 分组的 token 消耗排行。
2. **Given** 某个 skill 被调用多次，**When** 查看该 skill 的统计，**Then** 能看到平均 token 消耗和调用次数。

---

### User Story 3 - 累计费用估算 (Priority: P2)

As a developer, I can see the estimated cost based on model pricing so I can track my spending.

**Acceptance Scenarios**:

1. **Given** 使用的模型有已知定价，**When** 查看统计页面，**Then** 能看到累计费用估算（美元）。
2. **Given** 不同模型有不同定价，**When** 切换模型，**Then** 费用估算自动更新。

---

### User Story 4 - Context 使用率实时显示 (Priority: P3)

As a developer, I can see the current context window usage during a conversation so I know when compression will happen.

**Acceptance Scenarios**:

1. **Given** 正在进行对话，**When** 查看 CLI shell，**Then** 能看到当前 context 使用率（如 "3.2K / 128K tokens, 2.5%"）。
2. **Given** context 使用率超过 80%，**When** 继续对话，**Then** 有明显的警告提示。

---

## Requirements

### Functional Requirements

- **FR-001**: Agent 执行时 MUST 从 LLM API 响应中提取 `usage` 字段（`prompt_tokens`, `completion_tokens`, `total_tokens`）。
- **FR-002**: ExecutionTrace MUST 包含每轮 LLM 调用的 token 统计。
- **FR-003**: Trace JSON MUST 在每个 `llm_rounds` 中记录 `usage` 字段。
- **FR-004**: Trace viewer 详情页 MUST 显示每个 turn 的 token 消耗。
- **FR-005**: 系统 MUST 提供一个 token 统计 API，返回按 tool/skill 分组的消耗数据。
- **FR-006**: 系统 MUST 支持配置模型定价（input/output 单价），用于费用估算。
- **FR-007**: Token 统计页面 MUST 显示累计 token 消耗和估算费用。

### Key Entities

- **TokenUsage**: 单次 LLM 调用的 token 统计
  - `prompt_tokens`: int
  - `completion_tokens`: int
  - `total_tokens`: int

- **ModelPricing**: 模型定价配置
  - `model_name`: str
  - `input_price_per_1m`: float（每百万 input tokens 的价格，美元）
  - `output_price_per_1m`: float（每百万 output tokens 的价格，美元）

- **TokenStats**: 聚合统计
  - `total_conversations`: int
  - `total_turns`: int
  - `total_tokens`: int
  - `total_cost_usd`: float
  - `by_tool`: Dict[str, TokenUsage]（按 tool 分组）
  - `by_model`: Dict[str, TokenUsage]（按模型分组）

---

## Data Model

### ExecutionTrace 扩展

```python
class LLMRoundTrace(BaseModel):
    round_index: int
    request_messages: List[Dict[str, Any]]
    assistant_content: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    usage: Optional[Dict[str, int]] = None  # 新增
    # usage = {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
```

### Trace JSON Schema 扩展

```json
{
  "llm_rounds": [
    {
      "round_index": 1,
      "request_messages": [...],
      "assistant_content": "...",
      "tool_calls": [...],
      "tool_results": [...],
      "usage": {
        "prompt_tokens": 1234,
        "completion_tokens": 567,
        "total_tokens": 1801
      }
    }
  ]
}
```

### Model Pricing Config

```toml
# guabot.toml
[token_monitoring]
enabled = true

[[token_monitoring.model_pricing]]
model = "gpt-4.1-mini"
input_price_per_1m = 0.15
output_price_per_1m = 0.60

[[token_monitoring.model_pricing]]
model = "gpt-4o"
input_price_per_1m = 2.50
output_price_per_1m = 10.00
```

---

## Technical Architecture

```
src/guabot/
  agent.py                    # 提取 usage 并记录到 LLMRoundTrace
  token_stats.py              # 新增：token 统计聚合逻辑
  config.py                   # 扩展：支持 token_monitoring 配置

traces/
  viewer/
    src/app/
      stats/
        page.tsx              # 新增：token 统计页面
      api/
        token-stats/
          route.ts            # 新增：聚合统计 API
```

---

## Implementation Plan

### Phase 1: 基础数据采集（P1）

1. 修改 `agent.py`：
   - 在 `_run_llm_with_tool_loop` 中提取 `response.usage`
   - 将 usage 记录到 `LLMRoundTrace`

2. 修改 `tracing.py`：
   - 确保 `_llm_round_payload` 保留 `usage` 字段

3. 修改 `trace-detail-client.tsx`：
   - 在每个 LLMRound 卡片中显示 token 统计

### Phase 2: 聚合统计（P2）

1. 创建 `token_stats.py`：
   - `aggregate_token_stats(trace_dir)`: 扫描所有 trace JSON，聚合统计
   - `calculate_cost(usage, model_pricing)`: 根据定价计算费用

2. 创建 API route `api/token-stats/route.ts`：
   - 读取所有 trace 文件
   - 调用聚合逻辑
   - 返回统计数据

3. 创建统计页面 `stats/page.tsx`：
   - 显示总体统计（总 tokens、总费用）
   - 按 tool/skill 分组的消耗排行
   - 按模型分组的消耗

### Phase 3: 实时显示（P3，可选）

1. 在 CLI shell 中显示当前 context 使用率
2. 超过阈值时显示警告

---

## Success Criteria

- **SC-001**: 每个 trace JSON 的 `llm_rounds` 中包含 `usage` 字段，无遗漏。
- **SC-002**: Trace viewer 详情页能正确显示每轮的 token 消耗。
- **SC-003**: Token 统计页面能在 2 秒内加载并显示聚合数据。
- **SC-004**: 费用估算误差在 ±5% 以内（基于实际 API 账单验证）。

---

## Assumptions

- OpenAI API 响应中始终包含 `usage` 字段（实际情况确实如此）
- 模型定价相对稳定，手动配置即可（不需要实时从 API 获取）
- 初始版本只支持 OpenAI 兼容的 API（其他 LLM 提供商可能有不同的 usage 格式）
