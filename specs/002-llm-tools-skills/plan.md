# Implementation Plan: LLM 驱动决策与 Tools/Skills 联通验证

**Branch**: `002-llm-tools-skills` | **Date**: 2026-02-25 | **Spec**: [`spec.md`](./spec.md)
**Input**: Feature specification from `/specs/002-llm-tools-skills/spec.md`

**Note**: 本计划由 `/speckit.plan` 命令生成，用于指导“LLM 决策 + Tools/Skills 联通验证”特性的设计与实现。

## Summary

本特性的主要目标是：在现有 Guabot 脚手架上，引入一个可配置的 LLM 决策层，使其能够基于 IM 对话消息和最近上下文，自动判断是否以及如何调用已注册的 Tools/Skills，并完成一次端到端的 LLM + Tools + Skills 流程验证（至少一个真实 LLM 提供方 + 至少一个工具/Skill + 至少一个 IM 渠道）。

技术上，计划采用“轻量 HTTP/SDK 客户端 + 显式决策循环”的极简方式接入单一 LLM 提供方，在现有 `capabilities` 与 `pipeline` 结构上增加一层“LLM 决策与工具编排”模块，避免引入 LangChain 等重型框架。该模块负责：

- 将 IM 收到的用户消息与最近 N 条历史封装为 LLM 输入上下文；
- 暴露受控的工具/Skill 列表与调用约束给 LLM（提示词或轻量 schema）；
- 解析 LLM 输出中的“是否调用工具”“调用哪个工具”“如何组合多步调用”等意图，并驱动底层能力层执行；
- 将工具返回结果与 LLM 生成的自然语言回复融合，并在日志中输出完整执行轨迹，满足可观测性要求。

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.12（与现有脚手架保持一致）  
**Primary Dependencies**: 标准库 + 现有依赖（`httpx`、`pydantic` 等），LLM 接入层优先通过简单 HTTP/SDK 客户端实现，避免引入 LangChain/LlamaIndex 等重型框架  
**Storage**: 当前迭代以内存存储会话与执行轨迹摘要为主，不新增数据库或消息队列（长期审计能力留待后续特性）  
**Testing**: `pytest` 为主的单元与集成测试框架，结合现有 `tests/` 结构补充针对 LLM 决策与工具调用路径的测试任务  
**Target Platform**: Linux 服务器环境，主要通过命令行与 IM Webhook 形式接入  
**Project Type**: 单一后端项目（CLI/服务合一），源代码集中在 `src/guabot` 下  
**Performance Goals**: 以“人机对话场景的交互体验”作为基线：在测试环境中，大部分请求端到端响应时间控制在数秒级，LLM 决策与工具调用开销不明显拉长 IM 对话节奏；大规模并发与吞吐优化不在本次范围内  
**Constraints**: 必须遵循极简主义原则，不得引入重型编排框架；LLM 调用成本可控，需要通过配置限制最大工具调用轮数与并发度；日志中不得泄露敏感用户数据  
**Scale/Scope**: 本次迭代聚焦于少量 IM 渠道与内部测试用户，用例集规模在数十到百级对话，不面向大规模生产流量

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

根据《Guabot 宪章》自查：

- 极简主义：本计划明确约束仅使用 Python 标准库和现有轻量依赖，通过自建“LLM 决策 + 能力编排”模块完成逻辑，不引入 LangChain、LlamaIndex 等重型框架，也不增加额外的基础设施（数据库、消息队列），符合极简主义原则。
- 可验证行为：在 `specs/002-llm-tools-skills/spec.md` 中，所有 P1 用户故事均提供了 Given-When-Then 形式的可验证场景，本计划将在 Phase 2 的 `tasks.md` 中为关键 happy path（如“IM 中询问服务状态并触发工具调用”）安排自动化或半自动测试任务，满足“可验证行为与测试优先”的要求。
- 可观测性：LLM 调用与工具调用都属于外部依赖交互，本计划要求在执行链路中输出结构化日志（包括会话 ID、选中的工具名称、耗时与结果状态），并在需要时为调试视图提供基础追踪信息，符合宪章中对可观测性的要求。

当前设计未发现违反宪章的强制性约束，因此允许进入 Phase 0 研究阶段。

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
