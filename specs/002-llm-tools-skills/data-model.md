# Data Model: LLM 驱动决策与 Tools/Skills 联通验证

**Branch**: `002-llm-tools-skills`  
**Spec**: [`spec.md`](./spec.md)  
**Plan**: [`plan.md`](./plan.md)

本文件描述本特性涉及的核心领域实体、字段与关系，用于指导实现与测试设计。该数据模型聚焦于“LLM 决策 + Tools/Skills 编排 + 执行轨迹”相关概念，不涉及底层存储实现细节。

## 1. LLM 会话上下文（LLMContext）

表示 LLM 在一次决策时可见的输入上下文。

- **id**: 会话内唯一标识（可复用现有会话 ID 或本次决策 ID）
- **user_message**: 当前用户消息文本
- **history**: 最近 N 条对话历史（列表，包含角色、内容、时间等摘要）
- **available_capabilities**: 当前可用的工具/Skills 列表（名称、简要描述、必要参数说明）
- **channel**: 触发请求的渠道（IM 类型、机器人标识等）
- **metadata**: 其他与决策相关的上下文元数据（例如环境、租户信息等），以键值对形式表示

关系：

- 一个 `LLMContext` 对应一次 LLM 决策请求；
- 一个会话（Session）中可以包含多次 `LLMContext` 实例，对应多轮 LLM 调用。

## 2. 工具调用计划（ToolPlan）

表示 LLM 对工具/Skills 的调用意图，由决策层从 LLM 输出中解析得到。

- **id**: 计划唯一标识
- **session_id**: 所属会话 ID
- **llm_request_id**: 绑定的 LLM 请求标识（方便回溯）
- **steps**: 调用步骤列表，每个步骤包含：
  - **capability_name**: 要调用的工具或 Skill 名称
  - **arguments**: 结构化参数（键值对），在执行前会再次校验
  - **depends_on**: 依赖的前序步骤 ID 列表，用于表达简单的有向依赖关系
- **max_parallelism**: 允许的最大并行度（可选，用于约束并发调用）
- **notes**: LLM 给出的补充说明或自然语言理由（可选）

关系：

- 一个 `ToolPlan` 由一次 LLM 决策生成，可以包含 0～N 个步骤；
- `ToolPlan` 的步骤在执行时会产生对应的工具调用记录，并写入执行轨迹。

## 3. 执行轨迹（ExecutionTrace）

用于记录从接收用户消息到返回最终回复的关键节点，支撑可观测性与调试视图。

- **id**: 轨迹唯一标识
- **session_id**: 会话 ID
- **channel**: 渠道信息
- **steps**: 有序步骤列表，每个步骤包含：
  - **type**: 步骤类型（例如 `llm_request`、`tool_call`、`tool_result`、`final_reply` 等）
  - **timestamp**: 时间戳
  - **summary**: 本步骤的简要描述（例如“LLM 选择调用 get_service_status 工具”）
  - **duration_ms**: 耗时（如适用）
  - **status**: 状态（成功/失败/降级等）
  - **details**: 不含敏感信息的结构化详情（例如工具名称、错误码、截断后的结果摘要）

关系：

- 一个会话对应一个或多个 `ExecutionTrace`（按消息或按对话片段划分）；
- `ExecutionTrace.steps` 中的 `tool_call` / `tool_result` 步骤可关联到具体的能力调用（通过工具名称和调用 ID）。

## 4. 能力注册信息（CapabilityDescriptor）

表示对外暴露给 LLM 与编排层的工具/Skills 元信息（并非运行时实例）。

- **name**: 能力名称（唯一标识）
- **kind**: 类型（`tool` 或 `skill`）
- **description**: 自然语言描述，帮助 LLM 理解用途
- **input_schema**: 输入参数的结构描述（字段名、类型、是否必填、取值约束等）
- **output_schema**: 输出结果的结构描述（摘要级别，便于日志与调试）
- **enabled_for_llm**: 是否对 LLM 决策可见（布尔值，便于按环境/渠道控制）

关系：

- 多个 `CapabilityDescriptor` 通过某种注册表（例如内部的 `CapabilityRegistry`）暴露给 LLM 决策层和工具执行层；
- `LLMContext.available_capabilities` 可视为选取并序列化后的部分 `CapabilityDescriptor` 信息。

## 5. 渠道/会话封装（SessionMeta）

用于抽象 IM 渠道的会话信息，与具体 IM 平台解耦。

- **session_id**: 会话唯一标识（可能来源于 IM 平台会话 ID）
- **channel**: 渠道类型或标识（如某 IM 平台 + 机器人 ID）
- **user_id**: 用户标识（如匿名 ID 或内部账号 ID）
- **extra**: 与会话相关的额外元数据（例如语言偏好等）

关系：

- `SessionMeta` 与多次 `LLMContext`、`ExecutionTrace` 通过 `session_id` 关联；
- IM Webhook 层在收到消息时负责从原始请求中构建或查找对应的 `SessionMeta`。

