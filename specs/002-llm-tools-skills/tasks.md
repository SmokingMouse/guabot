# Tasks: LLM 驱动决策与 Tools/Skills 联通验证

**Input**: Design documents from `/specs/002-llm-tools-skills/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: 本特性在规格中明确了端到端回归与可验证行为，因此本任务列表中为关键用户故事添加了必要的测试任务（以集成测试为主），但依然保持测试集合的规模可控。

**Organization**: 任务按用户故事分组，每个故事对应一个独立 Phase，确保可以独立实现与验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 表示任务可并行执行（不同文件、无直接依赖）
- **[Story]**: 表示任务归属的用户故事（例如 US1, US2, US3）
- 所有任务描述中都包含明确的文件路径

## Path Conventions

- 单项目结构：源代码集中于 `src/guabot/`，测试位于根目录下 `tests/`

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 初始化与本特性相关的基础配置和能力注册骨架，为后续实现打好基础。

- [x] T001 在 `src/guabot/config.py` 中为单一 LLM 提供方新增配置结构（如 API Key、Base URL、超时等字段），并提供从环境变量加载的入口
- [x] T002 [P] 在 `src/guabot/capabilities.py` 中为示例工具/Skill（如“当前时间”“错误计数查询”）预留注册入口和占位实现，统一通过能力注册表暴露给决策层
- [x] T003 [P] 在 `src/guabot/pipeline.py` 中添加基础的结构化日志记录帮助函数，用于写入 ExecutionTrace 摘要（会话 ID、步骤类型、工具名、状态等）
- [x] T004 在 `tests/test_pipeline.py` 和 `tests/test_capabilities_tools.py` 中确认并整理测试入口结构，为后续增加 LLM 决策与工具调用相关用例预留清晰的分组

---

## Phase 2: Foundational（阻塞性前置能力）

**Purpose**: 实现所有用户故事共享的核心领域模型与执行骨架，未完成前不得开始各用户故事实现。

**⚠️ CRITICAL**: 本 Phase 必须全部完成，才能开始任一用户故事的实现。

- [ ] T005 在 `src/guabot/memory.py` 中定义 `LLMContext` 数据模型，字段与 `specs/002-llm-tools-skills/data-model.md` 中描述保持一致
- [ ] T006 [P] 在 `src/guabot/memory.py` 中定义 `ToolPlan` 及其步骤子结构（包含 capability_name、arguments、depends_on 等），用于表达 LLM 生成的工具调用计划
- [ ] T007 [P] 在 `src/guabot/memory.py` 中定义 `ExecutionTrace` 及 TraceStep 结构，用于记录完整的 LLM + Tools/Skills 执行轨迹
- [ ] T008 在 `src/guabot/capabilities.py` 中定义 `CapabilityDescriptor` 结构及能力注册表接口，支持按名称查找能力并暴露给 LLM 决策层
- [ ] T009 在 `src/guabot/agent.py` 中抽象 `SessionMeta`（会话 ID、channel、user_id 等），并实现从 IM Webhook 请求构建 `SessionMeta` 的辅助函数

**Checkpoint**: 完成以上任务后，领域模型、能力注册与基础执行轨迹结构应全部就绪，可开始按用户故事实现具体流程。

---

## Phase 3: User Story 1 - LLM 在 IM 中自动决策是否调用工具（Priority: P1） 🎯 MVP

**Goal**: 让 LLM 能够基于 IM 对话上下文自动判断是否调用某个工具/Skill，并在回复中融合调用结果；对于纯闲聊问题，则不调用工具，仅给出自然回复。

**Independent Test**: 在测试环境中，针对“现在时间是多少？”与“讲个笑话”等请求，通过 IM 发送消息验证：需要外部数据的问题会触发工具调用并融合结果，纯闲聊不会触发工具调用，且二者的执行路径在日志中可区分。

### Tests for User Story 1

- [ ] T010 [P] [US1] 在 `tests/test_pipeline.py` 中添加集成用例：模拟 `/im/webhook/guabot` 收到“现在时间是多少？”请求，验证 LLM 决策触发时间工具调用且回复内容包含具体时间
- [ ] T011 [P] [US1] 在 `tests/test_pipeline.py` 中添加集成用例：模拟收到“讲个笑话”请求，验证 LLM 决策不触发任何工具调用，并返回自然语言笑话（可通过 ExecutionTrace 或日志确认无工具调用步骤）

### Implementation for User Story 1

- [ ] T012 [P] [US1] 在 `src/guabot/pipeline.py` 中实现从 IM Webhook 请求构建 `LLMContext` 的函数，包含当前用户消息、最近 N 条对话历史和当前可用能力列表
- [ ] T013 [P] [US1] 在 `src/guabot/agent.py` 中实现对单一 LLM 提供方的 HTTP 调用封装（LLM 客户端），从 `config.LLMConfig` 读取凭证与超时，并返回标准化的 LLM 输出结构
- [ ] T014 [US1] 在 `src/guabot/pipeline.py` 中实现 LLM 决策层：根据 LLM 输出判断是否调用工具，并在需要时将意图解析为单步 `ToolPlan`
- [ ] T015 [US1] 在 `src/guabot/pipeline.py` 中实现单步工具调用执行逻辑：根据 `ToolPlan` 调用 `src/guabot/capabilities.py` 中注册的能力，并将结果与 LLM 回复内容融合
- [ ] T016 [US1] 在 `src/guabot/pipeline.py` 中为 LLM 请求、工具调用与最终回复写入 `ExecutionTrace`，生成 `trace_id` 并返回给 IM 通道集成层
- [ ] T017 [US1] 在 `main.py` 中接入 `/im/webhook/guabot` 路由（或现有 IM 集成入口），将 HTTP 请求参数转换为内部调用并委托给 `src/guabot/pipeline.py` 的决策流水线（参考 `specs/002-llm-tools-skills/contracts/llm-tools-flow.yaml`）

**Checkpoint**: 完成 Phase 3 后，应能在测试环境中通过 IM 触发“现在时间是多少？”与“讲个笑话”两个场景，并通过日志/ExecutionTrace 确认决策与工具调用链路正确。

---

## Phase 4: User Story 2 - LLM 驱动多步 Tools/Skills 调用（Priority: P2）

**Goal**: 让 LLM 能够在单轮对话中规划并执行多个工具/Skill 调用（如错误计数 + 版本信息），并将多个调用结果整理为一句话总结；当部分能力不可用时，也能优雅降级返回部分结果。

**Independent Test**: 在内部测试环境中，仅启用“错误计数查询”“版本信息查询”等示例能力，通过 IM 发出复合指令，验证多步工具调用的执行与降级行为，不依赖 US3 的调试视图即可判断故事是否完成。

### Tests for User Story 2

- [ ] T018 [P] [US2] 在 `tests/test_pipeline.py` 中添加集成用例：模拟“帮我查一下今天错误数和当前版本，并给个一句话总结”，验证至少两次不同能力被调用且回复中包含两项结果与一句话总结
- [ ] T019 [P] [US2] 在 `tests/test_pipeline.py` 中添加集成用例：模拟其中一个能力不可用（如模拟异常/超时），验证回复中说明某部分信息缺失，但仍返回其它可用信息且整体不报硬错误

### Implementation for User Story 2

- [ ] T020 [P] [US2] 在 `src/guabot/pipeline.py` 中扩展 `ToolPlan` 解析逻辑，使其支持 LLM 输出多步工具调用意图（包括步骤顺序与简单依赖关系）
- [ ] T021 [US2] 在 `src/guabot/pipeline.py` 中实现按照 `ToolPlan` 步骤顺序执行工具调用（支持串行执行，并通过 `max_parallelism` 限制简单并行），收集各步结果供最终汇总
- [ ] T022 [US2] 在 `src/guabot/pipeline.py` 中实现多步调用的部分失败降级策略：当单步失败时在 `ExecutionTrace` 中记录失败详情，并在最终回复中以自然语言说明缺失信息，同时继续返回其他成功结果
- [ ] T023 [US2] 在 `src/guabot/capabilities.py` 中实现示例能力“错误计数查询”和“版本信息查询”的具体逻辑与能力描述（`CapabilityDescriptor`），确保可被 LLM 决策层选择和调用

**Checkpoint**: 完成 Phase 4 后，应能在测试环境中通过复合指令触发多步工具调用，并正确处理部分失败场景，独立于 US3 的调试视图即可完成验收。

---

## Phase 5: User Story 3 - 可观测的 LLM + Tools + Skills 调试视图（Priority: P3）

**Goal**: 为开发/运维提供可观测能力，可以基于 `trace_id` 或会话 ID 回看某次对话完整的 LLM 决策与工具调用轨迹，并确保日志中不泄露敏感信息。

**Independent Test**: 在测试环境中对同一请求多次重放，收集日志或调用调试接口，验证可以基于会话 ID/trace_id 重建关键调用链，并通过人工检查确认未输出敏感字段。

### Tests for User Story 3

- [ ] T024 [P] [US3] 在 `tests/test_pipeline.py` 中添加用例：根据某次请求返回的 `trace_id`，通过内部接口或日志查询 `ExecutionTrace`，验证可恢复“LLM 决策 → 工具调用 → 结果 → 回复”的关键步骤摘要
- [ ] T025 [P] [US3] 在新的测试文件 `tests/test_observability.py` 中添加用例：构造包含模拟隐私字段的请求，验证结构化日志与 ExecutionTrace 中不会泄露明文敏感数据

### Implementation for User Story 3

- [ ] T026 [P] [US3] 在 `src/guabot/pipeline.py` 中实现统一的 ExecutionTrace 记录函数，确保在每个关键节点（LLM 请求、工具调用、最终回复）写入结构化日志
- [ ] T027 [US3] 在 `src/guabot/memory.py` 或新建轻量存储辅助结构中实现基于内存的 ExecutionTrace 存取接口，可按 `session_id` 与 `trace_id` 查询轨迹摘要
- [ ] T028 [US3] 在 `src/guabot/agent.py` 中实现用于调试的诊断函数（或 CLI 入口），根据 `trace_id` 输出人类可读的调用链摘要，便于快速排查“为什么没调用工具”等问题

**Checkpoint**: 完成 Phase 5 后，应能通过 `trace_id` 或会话 ID 在日志/调试视图中复原一次完整执行过程，并通过测试确认敏感信息得到妥善保护。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 跨用户故事的收尾工作与体验打磨。

- [ ] T029 [P] 在 `src/guabot/config.py` 中为 LLM 历史条数 N、最大工具调用步数与并行度等策略参数添加配置项与默认值，并在代码中使用这些配置替代硬编码
- [ ] T030 [P] 在 `src/guabot/capabilities.py` 与 `src/guabot/pipeline.py` 中梳理错误与日志文案，确保面向用户与运维的表述清晰一致
- [ ] T031 在 `specs/002-llm-tools-skills/quickstart.md` 中根据最终实现更新示例请求与预期行为描述，保证文档与实际行为一致
- [ ] T032 在项目根目录执行一次完整回归（如 `pytest`），并按 `specs/002-llm-tools-skills/spec.md` 中 SC-001～SC-004 的要求手工运行 Quickstart 场景，记录结果以支持验收

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1: Setup** — 无前置依赖，可立即开始
- **Phase 2: Foundational** — 依赖 Phase 1 完成，阻塞所有用户故事
- **Phase 3: User Story 1 (P1)** — 依赖 Phase 2 完成，是推荐的 MVP 首选故事
- **Phase 4: User Story 2 (P2)** — 依赖 Phase 2 完成，可在 US1 完成后或并行实现，但设计上可复用 US1 的基础能力
- **Phase 5: User Story 3 (P3)** — 依赖 Phase 2 完成，观察与调试视图可在 US1/US2 之后实现，也可在实现过程中按需补充
- **Phase 6: Polish** — 依赖所有目标用户故事完成后进行统一打磨

### User Story Dependencies

- **User Story 1 (P1)**: 基于基础领域模型与能力注册即可实现，不依赖其他用户故事，是最小可用闭环。
- **User Story 2 (P2)**: 复用 US1 的 LLM 决策与执行骨架，但在设计上保持独立验收路径；可在 US1 完成后开始，或与 US1 并行开发后分别验收。
- **User Story 3 (P3)**: 依赖 ExecutionTrace 与核心执行链，就绪后可对 US1 与 US2 提供统一的调试与可观测能力。

---

## Parallel Opportunities

- Phase 1 中标记为 [P] 的任务（T002, T003, T004）可并行执行，分别修改不同文件。
- Phase 2 中标记为 [P] 的任务（T006, T007）可在完成 T005 后并行推进，均位于 `src/guabot/memory.py`。
- 不同用户故事（Phase 3、4、5）在 Phase 2 完成后，可以按团队资源并行开发，但仍建议优先完成 US1 以获得 MVP。
- 各用户故事中标记为 [P] 的任务通常落在不同文件或相互独立的逻辑上，可由不同开发者分工协作。

---

## Parallel Example: User Story 1

在完成 Phase 2 后，可以针对 US1 并行推进以下任务：

- 并行 1：
  - T010 [P] [US1] 在 `tests/test_pipeline.py` 添加“现在时间是多少？”集成用例
  - T011 [P] [US1] 在 `tests/test_pipeline.py` 添加“讲个笑话”集成用例
- 并行 2：
  - T012 [P] [US1] 在 `src/guabot/pipeline.py` 实现构建 `LLMContext` 的函数
  - T013 [P] [US1] 在 `src/guabot/agent.py` 实现 LLM 客户端封装

待上述并行任务完成后，再串行完成 T014～T017 以打通整个端到端链路。

---

## Parallel Example: User Story 2

- 并行 1：
  - T018 [P] [US2] 在 `tests/test_pipeline.py` 添加多步工具调用成功场景用例
  - T019 [P] [US2] 在 `tests/test_pipeline.py` 添加部分失败场景用例
- 并行 2：
  - T020 [P] [US2] 在 `src/guabot/pipeline.py` 中扩展 `ToolPlan` 解析逻辑
  - T023 [US2] 在 `src/guabot/capabilities.py` 中实现示例能力（如错误计数与版本查询）

在上述任务完成后，再串行实现和调优执行与降级逻辑（T021, T022）。

---

## Parallel Example: User Story 3

- 并行 1：
  - T024 [P] [US3] 在 `tests/test_pipeline.py` 中添加基于 `trace_id` 恢复 ExecutionTrace 的用例
  - T025 [P] [US3] 在 `tests/test_observability.py` 中添加日志脱敏用例
- 并行 2：
  - T026 [P] [US3] 在 `src/guabot/pipeline.py` 中实现统一的 ExecutionTrace 记录函数
  - T027 [US3] 在 `src/guabot/memory.py` 中实现 ExecutionTrace 内存存取接口

最后再实现 T028，提供面向开发/运维的诊断入口。

---

## Implementation Strategy

### MVP 优先（仅 User Story 1）

1. 完成 Phase 1: Setup
2. 完成 Phase 2: Foundational（阻塞所有故事）
3. 完成 Phase 3: User Story 1（P1）
4. 使用 Quickstart 中的简单场景验证 US1 是否独立可用
5. 若效果满足预期，可作为 MVP 在内部试用或 Demo

### 渐进式交付

1. 完成 Phase 1 + Phase 2，确保基础结构稳定
2. 增量交付 US1 → 验证 → Demo/MVP
3. 在此基础上交付 US2（多步调用与降级）→ 验证 → Demo
4. 最后交付 US3（可观测与调试视图）→ 验证 → Demo
5. 每个故事的完成都在不破坏已有功能的前提下单独增加价值

### 并行开发策略

1. 团队先协作完成 Phase 1 + Phase 2
2. Phase 2 完成后：
   - 开发者 A 负责 US1（决策与单步工具调用）
   - 开发者 B 负责 US2（多步工具编排与降级）
   - 开发者 C 负责 US3（ExecutionTrace 持久化与调试视图）
3. 各故事开发完成后，通过 ExecutionTrace 与端到端用例进行联调与回归

---

## Notes

- 所有任务均采用 `- [ ] TXXX [P?] [US?] 描述` 的格式，便于机器与人类同时消费。
- 标记为 [P] 的任务可在不产生文件冲突的前提下并行执行，提高开发效率。
- 用户故事被设计为可独立验收：完成任一故事后，均可通过对应的测试与 Quickstart 步骤单独验证其价值。
- 建议在完成每个 Phase 或用户故事后进行一次小范围回归与 Demo，确保演进过程平滑可控。
