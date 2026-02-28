# Token Monitoring

Token 监控功能已实现，用于追踪和分析 LLM API 的 token 使用情况和成本。

## 功能特性

### ✅ Phase 1: 基础数据采集

- 自动从 OpenAI API 响应中提取 token usage
- 每轮 LLM 调用都记录 `prompt_tokens`、`completion_tokens`、`total_tokens`
- 数据持久化到 trace JSON 文件
- Trace Viewer 详情页显示每轮的 token 统计

### ✅ Phase 2: 聚合统计

- 聚合所有对话的 token 使用情况
- 按 tool/skill 分组统计
- 按对话分组统计
- 基于模型定价的费用估算
- 独立的统计页面展示

## 使用方法

### 1. 查看单次对话的 Token 使用

访问 Trace Viewer 详情页（`http://localhost:3000/<conversation_id>`），每个 turn 会显示：

- Turn 标题中显示总 token 数（蓝色徽章）
- 每个 LLM Round 显示详细的 token 统计：
  - Input tokens（prompt_tokens）
  - Output tokens（completion_tokens）
  - Total tokens

### 2. 查看聚合统计

访问统计页面（`http://localhost:3000/stats`），可以看到：

- **总体统计**：
  - 总费用（基于 gpt-4.1-mini 定价）
  - 对话数量和 turn 数量
  - 总 token 消耗
  - 平均每 turn 的 token 消耗

- **按 Tool 分组**：
  - 每个 tool 的 token 消耗排行
  - 调用次数统计

- **按对话分组**：
  - 最近 20 个对话的 token 使用情况
  - 点击可跳转到详情页

### 3. Python API

```python
from src.guabot.token_stats import aggregate_token_stats, calculate_total_cost

# 聚合统计
stats = aggregate_token_stats('traces/data')
print(f"Total tokens: {stats['total_usage']['total_tokens']}")
print(f"Total conversations: {stats['total_conversations']}")

# 计算费用
cost = calculate_total_cost(stats['total_usage'], model_name='gpt-4.1-mini')
print(f"Estimated cost: ${cost:.4f}")

# 按 tool 查看
for tool_name, usage in stats['by_tool'].items():
    print(f"{tool_name}: {usage['total_tokens']} tokens")
```

## 模型定价配置

当前支持的模型定价（USD per 1M tokens）：

| Model | Input | Output |
|-------|-------|--------|
| gpt-4.1-mini | $0.15 | $0.60 |
| gpt-4o | $2.50 | $10.00 |
| gpt-4o-mini | $0.15 | $0.60 |
| gpt-4-turbo | $10.00 | $30.00 |

如需添加自定义定价，修改 `src/guabot/token_stats.py` 中的 `DEFAULT_PRICING`。

## 数据格式

### Trace JSON 中的 usage 字段

```json
{
  "turns": [
    {
      "llm_rounds": [
        {
          "round_index": 1,
          "usage": {
            "prompt_tokens": 1234,
            "completion_tokens": 567,
            "total_tokens": 1801
          }
        }
      ]
    }
  ]
}
```

### 统计 API 响应格式

```json
{
  "total_conversations": 5,
  "total_turns": 37,
  "total_usage": {
    "prompt_tokens": 50000,
    "completion_tokens": 16644,
    "total_tokens": 66644,
    "count": 37
  },
  "by_tool": {
    "skill.version_info": {
      "prompt_tokens": 25000,
      "completion_tokens": 5096,
      "total_tokens": 30096,
      "count": 4
    }
  },
  "by_conversation": [...],
  "total_cost_usd": 0.0106
}
```

## 测试

```bash
# 运行 token stats 测试
python -m pytest tests/test_token_stats.py -v

# 测试聚合功能
python -c "from src.guabot.token_stats import aggregate_token_stats; print(aggregate_token_stats('traces/data'))"
```

## 下一步（Phase 3 - 可选）

- [ ] CLI shell 中实时显示 context 使用率
- [ ] 超过阈值时显示警告
- [ ] 支持更多 LLM 提供商的 usage 格式
- [ ] 导出统计报告（CSV/JSON）
