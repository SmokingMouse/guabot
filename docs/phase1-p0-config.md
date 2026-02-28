# Phase 1 P0 功能配置说明

本文档说明 Phase 1 P0 功能的配置选项。

## 功能概览

- **009-context-compression**: 上下文自动压缩,防止超过 context limit
- **010-tool-retry**: Tool 调用失败自动重试,提升健壮性
- **011-skill-timeout**: Skill 执行超时保护,防止 hang 住

## 配置文件位置

配置文件: `guabot.toml`

## 详细配置说明

### 1. 上下文压缩 (context_compression)

```toml
[context_compression]
enabled = true                    # 是否启用压缩功能
trigger_threshold = 0.8           # 触发压缩的使用率阈值 (0.0-1.0)
target_threshold = 0.6            # 压缩后的目标使用率 (0.0-1.0)
keep_recent_turns = 5             # 保留最近 N 轮对话不压缩
compression_model = "claude-haiku-4-5"  # 用于生成摘要的模型
max_summary_tokens = 100          # 每对消息的最大摘要 tokens
```

**工作原理**:
- 当 context 使用率超过 `trigger_threshold` (如 80%) 时自动触发压缩
- 将最旧的消息对合并为摘要,保留最近 `keep_recent_turns` 轮对话
- 压缩后使用率降至 `target_threshold` (如 60%) 以下

**调优建议**:
- 长对话场景: 降低 `trigger_threshold` 到 0.7,提前触发压缩
- 短对话场景: 提高 `trigger_threshold` 到 0.9,减少不必要的压缩
- 需要保留更多历史: 增加 `keep_recent_turns` 到 10

---

### 2. Tool 重试 (tool_retry)

```toml
[tool_retry]
enabled = true                    # 是否启用重试功能
default_max_retries = 3           # 默认最大重试次数
default_backoff_base = 1.0        # 退避基数 (秒)
max_total_retry_time = 30.0       # 总重试时间上限 (秒)
retryable_errors = [              # 可重试的错误类型
    "NetworkError",
    "TimeoutError",
    "RateLimitError",
    "ConnectionError"
]
non_retryable_errors = [          # 不可重试的错误类型
    "AuthenticationError",
    "InvalidInputError",
    "PermissionError"
]
```

**工作原理**:
- Tool 调用失败时,根据错误类型判断是否重试
- 使用指数退避策略: 1s, 2s, 4s, 8s...
- 记录每次重试的详细信息到 trace

**调优建议**:
- 网络不稳定环境: 增加 `default_max_retries` 到 5
- 快速失败场景: 减少 `default_max_retries` 到 1
- API 限流严格: 增加 `default_backoff_base` 到 2.0

---

### 3. Skill 超时 (skill_timeout)

```toml
[skill_timeout]
enabled = true                    # 是否启用超时功能
default_timeout = 60.0            # 默认超时时间 (秒)
grace_period = 5.0                # 优雅终止等待时间 (秒)
```

**工作原理**:
- 每个 skill 执行都有超时限制
- 超时后自动终止并返回错误
- 支持优雅终止 (发送 cancel 信号后等待 grace_period)

**调优建议**:
- 快速 skill (如计算): 设置 `default_timeout = 10.0`
- 慢速 skill (如爬虫): 设置 `default_timeout = 300.0`
- 需要快速响应: 减少 `grace_period` 到 2.0

---

## 禁用功能

如果需要临时禁用某个功能,将 `enabled` 设置为 `false`:

```toml
[context_compression]
enabled = false  # 禁用上下文压缩

[tool_retry]
enabled = false  # 禁用 tool 重试

[skill_timeout]
enabled = false  # 禁用 skill 超时
```

---

## 验证配置

运行以下命令验证配置是否正确加载:

```bash
python -c "
import sys
sys.path.insert(0, 'src')
from guabot.config import AppConfig
config = AppConfig.from_toml('guabot.toml')
print('✅ 配置加载成功!')
print(f'Context Compression: {config.context_compression.enabled}')
print(f'Tool Retry: {config.tool_retry.enabled}')
print(f'Skill Timeout: {config.skill_timeout.enabled}')
"
```

---

## 测试

运行单元测试验证功能:

```bash
# 测试所有 P0 功能
pytest tests/test_context_compression.py tests/test_tool_retry.py tests/test_skill_timeout.py -v

# 测试单个功能
pytest tests/test_context_compression.py -v
pytest tests/test_tool_retry.py -v
pytest tests/test_skill_timeout.py -v
```

---

## 监控

这些功能的执行信息会记录到 trace 中,可以通过以下方式查看:

1. **CLI Shell**: 实时显示工具调用状态
2. **Trace Viewer**: 查看详细的执行历史和压缩/重试/超时信息
3. **日志**: 检查 `logs/` 目录下的日志文件

---

## 故障排查

### 问题: 压缩触发过于频繁

**解决**: 提高 `trigger_threshold` 或增加 `keep_recent_turns`

### 问题: Tool 重试次数过多导致延迟

**解决**: 减少 `default_max_retries` 或缩短 `max_total_retry_time`

### 问题: Skill 经常超时

**解决**: 增加 `default_timeout` 或检查 skill 实现是否有性能问题

---

## 更多信息

- Spec 文档: `specs/009-context-compression/spec.md`
- Spec 文档: `specs/010-tool-retry/spec.md`
- Spec 文档: `specs/011-skill-timeout/spec.md`
- Roadmap: `specs/spec-final/roadmap.md`
