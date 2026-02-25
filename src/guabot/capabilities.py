from __future__ import annotations

import datetime as _dt
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Protocol


class Capability(Protocol):
    """能力抽象接口（工具 / Skill / MCP）。"""

    name: str
    kind: Literal["tool", "skill"]
    description: str

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:  # pragma: no cover - 协议本身无需测试
        ...


@dataclass
class CapabilityDescriptor:
    """对外暴露给 LLM 与编排层的能力元信息。"""

    name: str
    kind: Literal["tool", "skill"]
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    enabled_for_llm: bool = True


@dataclass
class TimeCapability:
    """示例能力：返回当前时间（UTC）。"""

    name: str = "time.now"
    kind: Literal["tool", "skill"] = "tool"
    description: str = "返回当前 UTC 时间戳，通常用于调试或在回复中展示时间信息。无参数。"

    def invoke(self, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        now = _dt.datetime.utcnow().isoformat() + "Z"
        return {"now": now}


@dataclass
class BashCapability:
    """简单的 Bash 工具能力。"""

    name: str = "shell.bash"
    kind: Literal["tool", "skill"] = "tool"
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
    """列出指定目录（非递归）的文件列表。"""

    name: str = "fs.ls"
    kind: Literal["tool", "skill"] = "tool"
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
                entries.append({"name": entry.name, "is_dir": entry.is_dir()})
            return {"path": str(path), "entries": entries}
        except Exception as exc:  # pragma: no cover - 防御性分支
            return {"path": str(path), "error": repr(exc)}


@dataclass
class ReadFileCapability:
    """读取本地文本文件的部分内容。"""

    name: str = "fs.read_file"
    kind: Literal["tool", "skill"] = "tool"
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
        return {"path": str(path), "content": content, "truncated": truncated}


@dataclass
class ErrorCountSkill:
    """示例 Skill：返回“今日错误数”。"""

    name: str = "skill.error_count"
    kind: Literal["tool", "skill"] = "skill"
    description: str = "查询今天的错误数。参数: service(str, 可选), unavailable(bool, 可选)。"

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if bool(arguments.get("unavailable")):
            return {"error": "service temporarily unavailable"}
        service = str(arguments.get("service", "core-api"))
        return {
            "service": service,
            "date": _dt.datetime.utcnow().strftime("%Y-%m-%d"),
            "error_count": 3,
        }


@dataclass
class VersionInfoSkill:
    """示例 Skill：返回当前版本。"""

    name: str = "skill.version_info"
    kind: Literal["tool", "skill"] = "skill"
    description: str = "查询当前部署版本。参数: service(str, 可选), unavailable(bool, 可选)。"

    def invoke(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if bool(arguments.get("unavailable")):
            raise RuntimeError("version service unavailable")
        service = str(arguments.get("service", "core-api"))
        return {"service": service, "version": "v0.1.0"}


class CapabilityRegistry:
    """简单的能力注册表。"""

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
        return list(self._capabilities.keys())

    def _build_input_schema(self, name: str) -> Dict[str, Any]:
        if name == "shell.bash":
            return {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
                "required": ["cmd"],
            }
        if name == "fs.read_file":
            return {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            }
        if name in {"fs.ls", "skill.error_count", "skill.version_info"}:
            return {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "service": {"type": "string"},
                    "unavailable": {"type": "boolean"},
                },
                "required": [],
            }
        return {"type": "object", "properties": {}, "required": []}

    def describe(self, name: str) -> CapabilityDescriptor:
        cap = self.get(name)
        if cap is None:
            raise KeyError(f"Capability '{name}' not found")
        return CapabilityDescriptor(
            name=cap.name,
            kind=getattr(cap, "kind", "tool"),
            description=getattr(cap, "description", ""),
            input_schema=self._build_input_schema(name),
            output_schema={"type": "object"},
            enabled_for_llm=True,
        )

    def available_details(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": d["name"],
                "kind": d["kind"],
                "description": d["description"],
            }
            for d in self.available_descriptors(llm_only=True)
        ]

    def available_descriptors(self, llm_only: bool = True) -> List[Dict[str, Any]]:
        descriptors: List[Dict[str, Any]] = []
        for name in self.available_names():
            descriptor = self.describe(name)
            if llm_only and not descriptor.enabled_for_llm:
                continue
            descriptors.append(asdict(descriptor))
        return descriptors


def default_registry() -> CapabilityRegistry:
    """返回包含基础示例能力的注册表。"""

    registry = CapabilityRegistry()
    registry.register(TimeCapability())
    registry.register(BashCapability())
    registry.register(LsCapability())
    registry.register(ReadFileCapability())
    registry.register(ErrorCountSkill())
    registry.register(VersionInfoSkill())
    return registry
