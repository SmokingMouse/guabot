# Feature Specification: CLI Shell

**Feature Branch**: `005-cli-shell`
**Created**: 2026-02-27
**Status**: ✅ Completed (2026-02-28)
**Implementation**:
- `src/guabot/cli/shell.py` - 主 shell 实现,实时工具调用展示
- `src/guabot/cli/slash_commands.py` - Slash 命令处理
- `src/guabot/cli/input_session.py` - 输入会话管理
- `src/guabot/cli/live_panel.py` - 实时面板显示
- `tests/test_cli_shell_stream.py` - 测试

**Input**: 给 guabot 套一个类似 claude code 这种的命令行壳，一方面能看到过程信息，另一方面也能更好用一点

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 实时看到工具调用过程 (Priority: P1)

As a user, I can see each tool call as it happens (name, args, status) so I understand what the agent is doing without waiting for the final reply.

**Why this priority**: The core pain point — the current console is a black box during execution.

**Independent Test**: Send a request that triggers 2+ tool calls; verify each call appears in the terminal before the final reply.

**Acceptance Scenarios**:

1. **Given** the agent calls `tool.shell`, **When** the call starts, **Then** the terminal shows `⚙ tool.shell` with the command, and updates to `✓` or `✗` when it finishes.
2. **Given** the agent is waiting for the LLM, **When** the call is in-flight, **Then** a spinner is visible so the user knows the process is alive.

---

### User Story 2 - 更好的输入体验 (Priority: P1)

As a user, I can navigate input history with arrow keys and edit multi-line messages so I don't have to retype long prompts.

**Why this priority**: Basic usability — the current `input()` loop has no history or editing.

**Independent Test**: Press ↑ after sending a message; verify the previous message is recalled.

**Acceptance Scenarios**:

1. **Given** I sent a previous message, **When** I press ↑, **Then** the previous message appears in the input field.
2. **Given** I want to send a multi-line message, **When** I press `Alt+Enter`, **Then** a newline is inserted without submitting.

---

### User Story 3 - Slash 命令 (Priority: P2)

As a user, I can type `/help`, `/clear`, `/history`, `/trace` to control the shell so I don't need to remember flags or restart the process.

**Why this priority**: Discoverability and control — mirrors the Claude Code UX pattern.

**Independent Test**: Type `/help`; verify a command list is printed. Type `/clear`; verify the screen clears.

**Acceptance Scenarios**:

1. **Given** I type `/help`, **Then** a list of available slash commands with descriptions is shown.
2. **Given** I type `/clear`, **Then** the terminal screen is cleared and a fresh prompt appears.
3. **Given** I type `/history`, **Then** the last N conversation turns are printed.
4. **Given** I type `/trace on`, **Then** subsequent replies include the full tool invocation trace.

---

### Edge Cases

- What happens if the agent loop errors mid-execution? The shell should print the error and return to the prompt without crashing.
- What if the LLM response is very long? Output should stream token-by-token rather than appearing all at once.
- What if the user presses Ctrl+C during a running call? The current call is cancelled and the prompt is restored.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The shell MUST display each tool call (name + key args) as it starts, with a live status indicator.
- **FR-002**: The shell MUST show a spinner while waiting for LLM responses.
- **FR-003**: The shell MUST stream the final LLM text reply token-by-token.
- **FR-004**: The shell MUST support readline-style input history (↑/↓ navigation).
- **FR-005**: The shell MUST support multi-line input via `Alt+Enter`.
- **FR-006**: The shell MUST handle `/help`, `/clear`, `/history [n]`, `/trace on|off` slash commands.
- **FR-007**: The shell MUST handle Ctrl+C gracefully: cancel in-flight call, restore prompt.
- **FR-008**: The shell MUST handle Ctrl+D as a clean exit.
- **FR-009**: Tool call output (stdout/stderr) MUST be collapsible — shown inline but foldable on demand.

### Non-Functional Requirements

- **NFR-001**: Shell startup time MUST be under 1 second.
- **NFR-002**: The shell MUST work in any standard terminal (no GUI dependency).
- **NFR-003**: The shell MUST degrade gracefully in non-TTY environments (e.g. piped input).

### Key Entities

- **Shell**: The top-level REPL loop — owns input, rendering, and slash command dispatch.
- **LivePanel**: The transient display area showing in-progress tool calls and spinner.
- **ToolCallRow**: One line in the LivePanel representing a single tool invocation (name, args, status, latency).
- **SlashCommand**: A `/cmd` handler registered by name with a description and callback.
- **InputSession**: Wraps `prompt_toolkit` session — owns history file and key bindings.

## Architecture

```
src/guabot/cli/
  shell.py          # Shell class: REPL loop, slash command dispatch
  live_panel.py     # LivePanel: rich Live display for in-progress tool calls
  input_session.py  # InputSession: prompt_toolkit wrapper
  slash_commands.py # Built-in slash command handlers
  run_console.py    # (existing) updated to call Shell instead of raw input()
```

### Rendering Stack

- `rich` — spinner, styled text, live display, markdown rendering of final reply
- `prompt_toolkit` — input with history, key bindings, multi-line support

### Tool Call Display Format

```
  ⚙  skill.run  claude-code  …          ← in-progress (spinner)
  ✓  tool.shell  ls -la  (142ms)        ← success
  ✗  tool.shell  rm -rf /  (12ms)       ← failure
```

### Streaming

The agent executor needs a streaming variant: `run_with_trace_stream()` that yields either:
- `ToolCallEvent(name, args)` — tool started
- `ToolResultEvent(name, status, latency_ms)` — tool finished
- `TextChunk(text)` — LLM token
- `DoneEvent(trace)` — loop complete

The shell consumes this stream and updates the LivePanel and output area accordingly.

## Assumptions

- `rich` and `prompt_toolkit` will be added as dependencies.
- The agent executor will be extended with a streaming interface; the existing `run_with_trace` stays for non-TTY use.
- History is persisted to `~/.guabot/shell_history` (or `data_dir/shell_history`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every tool call appears in the terminal within 100ms of being dispatched.
- **SC-002**: Input history persists across shell restarts.
- **SC-003**: `/help` lists all slash commands correctly on first invocation.
- **SC-004**: Ctrl+C during a tool call returns to prompt without killing the process.
