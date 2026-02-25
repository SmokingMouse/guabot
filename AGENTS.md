# guabot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-02-25

## Active Technologies
- Python 3.12（与现有脚手架一致） (002-llm-tools-skills)
- 延续现有方案，首版仅使用内存存储会话与执行轨迹摘要；如需长期审计，在后续 (002-llm-tools-skills)
- Python 3.12（与现有脚手架保持一致） + 标准库 + 现有依赖（`httpx`、`pydantic` 等），LLM 接入层优先通过简单 HTTP/SDK 客户端实现，避免引入 LangChain/LlamaIndex 等重型框架 (002-llm-tools-skills)
- 当前迭代以内存存储会话与执行轨迹摘要为主，不新增数据库或消息队列（长期审计能力留待后续特性） (002-llm-tools-skills)

- Python 3.12 + `httpx`（HTTP 客户端）、`pydantic`（配置和消息模型）、`anyio` (001-agent-scaffold)

## Project Structure

```text
src/
tests/
```

## Commands

cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style

Python 3.12: Follow standard conventions

## Recent Changes
- 002-llm-tools-skills: Added Python 3.12（与现有脚手架保持一致） + 标准库 + 现有依赖（`httpx`、`pydantic` 等），LLM 接入层优先通过简单 HTTP/SDK 客户端实现，避免引入 LangChain/LlamaIndex 等重型框架
- 002-llm-tools-skills: Added Python 3.12（与现有脚手架一致）

- 001-agent-scaffold: Added Python 3.12 + `httpx`（HTTP 客户端）、`pydantic`（配置和消息模型）、`anyio`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
