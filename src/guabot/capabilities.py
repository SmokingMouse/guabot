from __future__ import annotations

import datetime as _dt
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Protocol


class Capability(Protocol):
    """能力抽象接口（工具 / Skill / MCP）。"""

    name: str
    description: str

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - 协议本身无需测试
        ...


@dataclass
class TimeCapability:
    """示例能力：返回当前时间（UTC）。

    仅用于验证工具调用链路，不涉及具体业务。
    """

    name: str = "time.now"
    description: str = "返回当前 UTC 时间戳，通常用于调试或在回复中展示时间信息。无参数。"

    def invoke(self, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = _dt.datetime.utcnow().isoformat() + "Z"
        return {"now": now}


@dataclass
class BashCapability:
    """简单的 Bash 工具能力。

    - 参数：
      - `cmd`: 必填，要执行的命令字符串，例如 `ls -la`、`cat README.md`。
    - 约束：
      - 仅用于短时间、只读或轻量调试命令；
      - 默认超时时间 5 秒，并截断输出，避免卡死或输出过大。
    """

    name: str = "shell.bash"
    description: str = "在运行环境中执行短时 Bash 命令，返回 exit_code/stdout/stderr，用于调试和查看状态。参数: cmd(str)。"
    timeout_seconds: float = 5.0
    max_output_chars: int = 4000

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cmd = str(arguments.get("cmd", "")).strip()
        if not cmd:
            return {"error": "cmd is required"}

        try:
            completed = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            stdout = (completed.stdout or "")[: self.max_output_chars]
            stderr = (completed.stderr or "")[: self.max_output_chars]
            return {
                "cmd": cmd,
                "exit_code": completed.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": len(completed.stdout or "") > self.max_output_chars,
            }
        except subprocess.TimeoutExpired:
            return {"cmd": cmd, "error": "timeout", "exit_code": None}
        except Exception as exc:  # pragma: no cover - 防御性分支
            return {"cmd": cmd, "error": repr(exc), "exit_code": None}


@dataclass
class LsCapability:
    """列出指定目录（非递归）的文件列表。

    - `path`: 要列出的路径，默认 "."（当前工作目录）。
    """
    name: str = "fs.ls"
    description: str = "列出指定目录下的直接子项（文件和子目录），不递归。参数: path(str, 可选, 默认当前目录)。"

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = arguments.get("path", ".")
        try:
            path = Path(str(raw_path)).expanduser().resolve()
        except Exception:
            return {"path": raw_path, "error": "invalid path"}

        if not path.exists():
            return {"path": str(path), "error": "path does not exist"}

        try:
            entries = []
            for entry in sorted(path.iterdir()):
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                    }
                )
            return {"path": str(path), "entries": entries}
        except Exception as exc:  # pragma: no cover - 防御性分支
            return {"path": str(path), "error": repr(exc)}


class CapabilityRegistry:
    """简单的能力注册表。

    未来可以在此处挂接真实的 Skills/MCP 客户端，目前仅提供内存级实现。
    """

    def __init__(self) -> None:
        self._capabilities: Dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def get(self, name: str) -> Capability | None:
        return self._capabilities.get(name)

    def invoke(self, name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        capability = self.get(name)
        if capability is None:
            raise KeyError(f"Capability '{name}' not found")
        return capability.invoke(arguments or {})

    def available_names(self) -> List[str]:
        """返回当前已注册能力名称列表。"""

        return list(self._capabilities.keys())

    def available_details(self) -> List[Dict[str, Any]]:
        """返回带描述的能力信息，供 LLM 构建决策上下文使用。"""

        details: List[Dict[str, Any]] = []
        for cap in self._capabilities.values():
            details.append(
                {
                    "name": cap.name,
                    "description": getattr(cap, "description", ""),
                }
            )
        return details


@dataclass
class ReadFileCapability:
    """读取本地文本文件的部分内容。

    - 参数：
      - `path`: 必填，要读取的文件路径；
    - 行为：
      - 读取文件前若干字节（默认 4096），并尝试按 UTF-8 解码；
      - 如果文件较大，仅返回前缀内容，并在结果中标记 `truncated`。"""

    name: str = "fs.read_file"
    description: str = "读取本地文本文件的前若干字节，用于快速查看文件内容。参数: path(str)。"
    max_bytes: int = 4096

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = arguments.get("path")
        if not raw_path:
            return {"error": "path is required"}

        try:
            path = Path(str(raw_path)).expanduser().resolve()
        except Exception:
            return {"path": raw_path, "error": "invalid path"}

        if not path.exists() or not path.is_file():
            return {"path": str(path), "error": "path does not exist or is not a file"}

        try:
            data = path.read_bytes()
        except Exception as exc:
            return {"path": str(path), "error": repr(exc)}

        truncated = len(data) > self.max_bytes
        prefix = data[: self.max_bytes]
        content = prefix.decode("utf-8", errors="replace")

        return {
            "path": str(path),
            "content": content,
            "truncated": truncated,
        }


def default_registry() -> CapabilityRegistry:
    """返回包含基础示例能力的注册表。"""

    registry = CapabilityRegistry()
    registry.register(TimeCapability())
    registry.register(BashCapability())
    registry.register(LsCapability())
    registry.register(ReadFileCapability())
    return registry
