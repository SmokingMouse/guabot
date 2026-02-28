# guabot Roadmap — 从单 Agent 能力到自规划

**状态**: Phase 1-2 基础功能已完成
**最后更新**: 2026-02-28

---

## 核心问题

guabot 当前在单一对话流中完成复杂需求的能力偏弱。
自规划能力的前提是：单 Agent 能可靠地完成任务。

---

## 阶段划分

```
Phase 1  基础能力夯实        ✅ 已完成
Phase 2  可观测性 & 调优工具  ✅ 基础完成
Phase 3  Claude Code 集成    ← 当前重点
Phase 4  自规划 Session
```

---

## Phase 1 — 单 Agent 基础能力夯实

**目标**：guabot 能在单一对话流中可靠地完成中等复杂度的任务。

### 1.1 Prompt 工程
- [x] 系统 prompt 模版化：角色定义、能力边界、输出格式规范 (prompts.py)
- [x] 任务状态注入：task_state.py 实现并集成到 pipeline (007-task-state-injection)
- [ ] Message 机制设计：何时压缩、何时截断、关键上下文如何保留
- [ ] Tool use 指令优化：减少 agent 乱调工具 / 不调工具的情况
- [ ] Few-shot 示例注入：针对高频任务类型

### 1.2 上下文管理
- [x] 实现 context window 使用率监控（当前用了多少 token）(token_stats.py)
- [x] 滑动窗口压缩策略：超阈值时自动摘要旧消息 → **spec 009-context-compression ✅**
- [ ] 关键信息 pin 机制：某些消息不参与压缩

### 1.3 Tool / Skill 健壮性
- [x] Tool 调用失败的重试 + 降级策略 → **spec 010-tool-retry ✅**
- [x] Skill 执行超时处理 → **spec 011-skill-timeout ✅**
- [ ] 工具结果过长时的截断 + 摘要

---

## Phase 2 — 可观测性 & 调优工具

**目标**：能看到 agent 在做什么、哪里出了问题，有数据支撑调优。

### 2.1 CLI Shell（已有 spec 005）
- [x] 实时工具调用展示（⚙ → ✓/✗）(cli/shell.py)
- [x] Token 流式输出 (cli/shell.py)
- [x] Slash 命令（/trace, /history, /clear）(cli/slash_commands.py)

### 2.2 Trace Viewer（已有 spec 006）
- [x] 每次对话自动写 trace JSON (tracing.py)
- [ ] Next.js viewer：对话列表 + 详情
- [ ] Message 生命周期可视化（active / compressed / expired）

### 2.3 Token 消耗监控（已有 spec 008）
- [x] 每次对话的 input/output token 统计 (token_stats.py)
- [x] 按 skill / tool 分类的 token 消耗分布 (token_stats.py)
- [x] 累计费用估算（基于模型定价）(token_stats.py)
- [x] 在 CLI shell 中实时显示当前 context 使用率 (集成到 shell.py)

### 2.4 决策追溯（新增）
- [ ] 记录 agent 每次 tool 选择的理由（从 LLM response 中提取）
- [ ] 标记"无效循环"：agent 重复调用同一工具 N 次未推进
- [ ] 在 trace viewer 中高亮异常决策路径

---

## Phase 3 — Claude Code 集成

**目标**：引入 Claude Code 作为编程辅助，加速 guabot 自身的迭代。

### 3.1 开发工作流
- [x] CLAUDE.md 完善：项目约定、常用命令、架构说明
- [ ] 用 Claude Code 辅助编写 skill（给出 spec → 生成代码 → 测试）
- [ ] 用 Claude Code 分析 trace：把 trace JSON 喂给 Claude Code 做问题诊断

### 3.2 guabot 调用 Claude Code（进阶）
- [ ] 将 Claude Code 封装为 guabot 的一个 skill
- [ ] guabot 可以委托 Claude Code 完成编程子任务
- [ ] 实现"guabot 写自己的 skill"的闭环

---

## Phase 4 — 自规划 Session

**目标**：实现 vision.md 中描述的自主循环代理。

> 前置条件：Phase 1-3 完成，单 Agent 能力稳定可靠。

- [ ] Session 抽象（对话 session + 自规划 session）
- [ ] Goal 定义 + 成功指标（agent 推断草稿，用户确认）
- [ ] 任务树自动分解
- [ ] Execute → Observe → Reflect → Replan 循环
- [ ] 反思 agent（触发检测 + 归因 + 报告）
- [ ] 调度器（cron + 事件 + agent 自主）
- [ ] Message Bus（多 agent 通信）
- [ ] Guardrails 引擎

---

## 已知痛点案例

### 案例 1：上下文丢失 / 意图错位
**现象**：让查找 skill → 找到了；让安装 → 安装成功；让移动到另一个目录 → agent 又执行了 skill 查找。
**可能原因**：
- 多轮对话后，早期的"查找"意图在 message 历史中权重过高，新指令被错误关联
- Tool result 过长导致关键上下文被压缩/截断，agent 丢失了"当前任务状态"
- System prompt 缺少"当前任务阶段"的显式标记，agent 每轮重新推断意图

**诊断方向**：用 trace viewer 看这次对话的 message 历史，确认哪一轮开始出现错位。

---



---

## 优先级建议

~~当前最值得投入的三件事（按 ROI 排序）：~~

~~1. **任务状态注入（Phase 1.1 优先）**：直接解决上下文错位，轻量版先验证效果~~
~~2. **Trace Viewer（006）**：能看到问题在哪，是所有调优的基础~~
~~3. **Token 监控**：成本可见，避免盲目消耗~~

✅ **Phase 1 P0 功能已完成**

**已完成的 P0 功能**:
1. ✅ **009-context-compression** - 滑动窗口压缩策略 (7 个测试通过)
2. ✅ **010-tool-retry** - Tool 重试 + 降级 (13 个测试通过)
3. ✅ **011-skill-timeout** - Skill 超时处理 (8 个测试通过)

**下一步建议**:
- 实际使用验证 Phase 1 P0 功能的稳定性
- 根据使用情况决定是否实现 P1 功能
- 或者开始 Phase 3 (Claude Code 集成) / Phase 4 (自规划 Session) 规划

---

## 开发模式建议（Claude Code 辅助）

- 每个节点对应一个 spec 文件，写清楚 user story + acceptance criteria
- 用 Claude Code 实现，用 trace viewer 验证效果
- 发现问题 → 更新 spec → 重新实现，小循环快速迭代
- Token 监控帮你控制每次 Claude Code session 的成本
