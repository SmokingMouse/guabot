# Guabot

本项目后端部分采用 Python 实现，并遵循《Guabot 宪章》中定义的开发原则。

核心原则之一是 **极简主义（Less is More）**：

- 拒绝使用 LangChain、LlamaIndex 等重型框架；
- 核心逻辑以清晰的 HTTP 客户端 + while 循环实现；
- 在满足需求的前提下保持依赖和抽象层级尽可能简单。

更多原则与治理规则详见 `.specify/memory/constitution.md`。
