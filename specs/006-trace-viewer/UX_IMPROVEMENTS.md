# Trace Viewer UX 优化

针对长对话场景的导航和可用性优化。

## 优化内容

### 1. 侧边导航栏（Sidebar Navigation）

**触发条件**：当对话超过 3 个 turns 时自动显示

**功能**：
- 显示所有 turns 的列表
- 点击快速跳转到对应 turn（平滑滚动）
- 有错误的 turn 用红色高亮显示（⚠ 图标）
- 显示每个 turn 使用的 tools
- 固定定位（sticky），滚动时始终可见
- 最大高度限制，内容可滚动

**操作按钮**：
- ⊕ Expand all - 展开所有 turns
- ⊖ Collapse all - 折叠所有 turns

### 2. Turn 折叠功能（Collapsible Turns）

**默认状态**：
- 第一个 turn 默认展开
- 其他 turns 默认折叠

**折叠时显示**：
- Turn 编号
- 错误标记（如果有）
- Tool 数量
- 时间戳
- Message 状态
- Token 消耗
- User message 前 100 字符预览

**展开时显示**：
- 完整的 turn 内容（user message、tool calls、assistant reply、API messages）

**交互**：
- 点击 turn 标题切换展开/折叠
- 通过侧边栏跳转时自动展开目标 turn
- 展开/折叠状态在页面刷新后不保留（每次重新加载时重置）

### 3. 回到顶部按钮（Back to Top）

**触发条件**：向下滚动超过 400px 时显示

**位置**：右下角固定定位

**功能**：点击平滑滚动回到页面顶部

**样式**：圆形按钮，带阴影，向上箭头图标

### 4. 响应式布局

**大屏幕（lg+）**：
- 侧边栏 + 主内容区域（flex 布局）
- 侧边栏宽度 256px（w-64）

**小屏幕（< lg）**：
- 隐藏侧边栏
- 主内容区域占满宽度
- 依然可以使用折叠功能

## 使用场景

### 场景 1：快速定位错误

1. 打开长对话的 trace
2. 查看侧边栏，红色高亮的 turn 表示有错误
3. 点击跳转到错误 turn
4. Turn 自动展开，查看错误详情

### 场景 2：浏览长对话

1. 打开长对话的 trace
2. 所有 turns 默认折叠，页面简洁
3. 点击感兴趣的 turn 标题展开查看
4. 查看完毕后点击标题折叠

### 场景 3：对比多个 turns

1. 使用侧边栏快速在不同 turns 之间跳转
2. 点击"Expand all"展开所有 turns
3. 滚动浏览所有内容
4. 使用"Back to top"按钮快速返回顶部

## 技术实现

### 状态管理

```typescript
const [expandedTurns, setExpandedTurns] = useState<Set<number>>(new Set([1]));
const [showBackToTop, setShowBackToTop] = useState(false);
```

### 平滑滚动

```typescript
const scrollToTurn = (turnId: number) => {
  const element = document.getElementById(`turn-${turnId}`);
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
    setExpandedTurns((prev) => new Set(prev).add(turnId));
  }
};
```

### 滚动监听

```typescript
useEffect(() => {
  const handleScroll = () => {
    setShowBackToTop(window.scrollY > 400);
  };
  window.addEventListener("scroll", handleScroll);
  return () => window.removeEventListener("scroll", handleScroll);
}, []);
```

## 性能考虑

- 折叠的 turns 不渲染详细内容，减少 DOM 节点数量
- 侧边栏使用虚拟滚动（max-height + overflow-y-auto）
- 平滑滚动使用 CSS `scroll-behavior: smooth`
- 状态更新使用 Set 数据结构，O(1) 查找复杂度

## 未来优化方向

- [ ] 添加搜索功能（搜索 tool 名称、错误信息等）
- [ ] 添加过滤功能（只显示有错误的 turns、特定 tool 的 turns）
- [ ] 支持键盘快捷键（j/k 上下导航，Enter 展开/折叠）
- [ ] 记住展开/折叠状态（localStorage）
- [ ] 添加"跳转到下一个错误"按钮
- [ ] 支持导出选中的 turns
