# Data Model: Agent 脚手架

**Feature**: `001-agent-scaffold`

## 会话（Conversation）

- **说明**：表示在某个 IM 渠道中的一段连续对话，是记忆与路由的基本单元。
- **关键字段**：
  - `id`: 全局唯一会话标识（字符串/UUID）
  - `channel_type`: 渠道类型（如 `feishu`、`slack`、`wechat_work` 等）
  - `channel_conversation_id`: 渠道侧会话标识（群/私聊 ID 等）
  - `user_id`: 触发会话的用户标识（如企业内部员工 ID）
  - `created_at`: 会话创建时间
  - `updated_at`: 最近一次消息时间
  - `memory_window`: 当前会话使用的记忆窗口 N（可继承自渠道默认值）
  - `status`: 会话状态（如 `active`、`archived`）

## 消息（Message）

- **说明**：会话中的一条用户或 Agent 消息，也是记忆窗口的基本元素。
- **关键字段**：
  - `id`: 全局唯一消息标识
  - `conversation_id`: 所属会话 ID
  - `direction`: 方向（`incoming` 用户→Agent，`outgoing` Agent→用户）
  - `sender_type`: 发送方类型（`user` / `agent` / `system`）
  - `timestamp`: 发送时间
  - `content`: 文本内容摘要（原文可视情况截断）
  - `raw_payload`: 渠道返回的原始消息结构（可选，便于调试）
  - `tool_calls`: 本条消息触发的能力调用列表（可选，见下文）

## 能力（Capability）

- **说明**：供 Agent 调用的外部能力抽象，统一封装工具 / Skills / MCP。
- **关键字段**：
  - `id`: 能力唯一标识
  - `name`: 人类可读名称
  - `type`: 能力类型（`tool` / `skill` / `mcp` / 其它）
  - `description`: 能力用途的简要说明
  - `config`: 协议/端点相关配置（例如 HTTP URL、MCP server 地址等）
  - `enabled`: 是否启用

## 能力调用（CapabilityInvocation）

- **说明**：一次从 Agent 发起的外部能力调用记录，用于调试与审计。
- **关键字段**：
  - `id`: 调用唯一标识
  - `conversation_id`: 所属会话 ID
  - `message_id`: 触发调用的消息 ID
  - `capability_id`: 被调用的能力 ID
  - `request_payload`: 发送给能力的请求参数（文本/JSON 摘要）
  - `response_payload`: 能力返回的结果（文本/JSON 摘要）
  - `status`: 调用结果（`success` / `failed` / `timeout` 等）
  - `latency_ms`: 调用耗时（毫秒）

## 渠道配置（ChannelConfig）

- **说明**：针对不同 IM 渠道的接入与行为配置。
- **关键字段**：
  - `id`: 渠道配置 ID
  - `channel_type`: 渠道类型
  - `webhook_url` / `callback_endpoint`: 回调地址等信息
  - `polling_interval_sec`: 如果需要轮询时的时间间隔
  - `default_memory_window`: 渠道默认记忆窗口 N
  - `max_memory_window`: 渠道允许设置的最大记忆窗口
  - `enabled_capabilities`: 该渠道允许使用的能力 ID 列表

## 状态与约束

- 对于每个会话：
  - 系统只需保留最近 `memory_window` 条消息用于上下文；
  - 当消息数超过 `memory_window` 或全局上限时，从最早消息开始丢弃。
- 所有实体以简单的 Python 对象/数据类为主，首版实现不强制持久化，仅在内存中维护；
  后续如接入 Redis/数据库，可在此数据模型基础上扩展。

