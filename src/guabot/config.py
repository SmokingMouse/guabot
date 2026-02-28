from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import os
try:  # py3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 兼容本地 py3.10 测试环境
    import tomli as tomllib


@dataclass
class McpServerConfig:
    """单个 MCP Server 配置。"""

    id: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)


@dataclass
class ChannelConfig:
    """单个 IM 渠道配置。

    这里只描述与脚手架强相关的最小字段，便于后续扩展。
    """

    channel_type: str
    default_memory_window: int = 20
    max_memory_window: int = 200
    token: str | None = None
    poll_interval_seconds: float = 2.0
    message_timeout_seconds: float = 60.0
    max_concurrent_conversations: int = 10
    proxy: str | None = None
    verify_ssl: bool = True
    app_id: str | None = None
    app_secret: str | None = None
    verification_token: str | None = None
    listen_host: str | None = None
    listen_port: int | None = None


@dataclass
class SkillsConfig:
    """Skills 目录配置。"""

    default_dirs: List[str] = field(default_factory=list)
    extension_dirs: List[str] = field(default_factory=list)

    def all_dirs(self) -> List[tuple]:
        """返回 [(path, source_type), ...] 列表，default 优先。"""
        result = [(d, "default") for d in self.default_dirs]
        result += [(d, "extension") for d in self.extension_dirs]
        return result


@dataclass
class ContextCompressionConfig:
    """上下文压缩配置"""

    enabled: bool = True
    trigger_threshold: float = 0.8
    target_threshold: float = 0.6
    keep_recent_turns: int = 5
    compression_model: str = "claude-haiku-4-5"
    max_summary_tokens: int = 100


@dataclass
class ToolRetryConfig:
    """Tool 重试配置"""

    enabled: bool = True
    default_max_retries: int = 3
    default_backoff_base: float = 1.0
    max_total_retry_time: float = 30.0
    retryable_errors: List[str] = field(default_factory=lambda: [
        "NetworkError", "TimeoutError", "RateLimitError", "ConnectionError"
    ])
    non_retryable_errors: List[str] = field(default_factory=lambda: [
        "AuthenticationError", "InvalidInputError", "PermissionError"
    ])


@dataclass
class SkillTimeoutConfig:
    """Skill 超时配置"""

    enabled: bool = True
    default_timeout: float = 60.0
    grace_period: float = 5.0


@dataclass
class AppConfig:
    """脚手架运行时配置（简化版）。"""

    channels: Dict[str, ChannelConfig] = field(default_factory=dict)
    llm: Optional["LLMConfig"] = None
    mcp_servers: List[McpServerConfig] = field(default_factory=list)
    data_dir: Optional[str] = None          # .guabot 根目录（绝对路径）
    memory_extractor_interval: int = 0   # minutes; 0 = disabled
    profile_updater_interval: int = 0    # minutes; 0 = disabled
    task_state_ttl_seconds: int = 1800
    skills: "SkillsConfig" = field(default_factory=SkillsConfig)
    context_compression: "ContextCompressionConfig" = field(default_factory=ContextCompressionConfig)
    tool_retry: "ToolRetryConfig" = field(default_factory=ToolRetryConfig)
    skill_timeout: "SkillTimeoutConfig" = field(default_factory=SkillTimeoutConfig)

    @property
    def memory_dir(self) -> Optional[str]:
        return str(Path(self.data_dir) / "memory") if self.data_dir else None

    @classmethod
    def minimal(cls) -> "AppConfig":
        """返回一个最小可用配置，供示例和测试使用。"""

        default_channel = ChannelConfig(channel_type="demo")
        return cls(channels={default_channel.channel_type: default_channel})

    @classmethod
    def from_toml(cls, path: str | Path) -> "AppConfig":
        """从 TOML 配置文件加载 AppConfig。

        当前约定的结构示例：

        [llm]
        endpoint = "https://openrouter.ai/api/v1"
        api_key = "sk-..."
        model = "openrouter/openai/gpt-4.1-mini"
        timeout = 10.0

        [channels.demo]
        default_memory_window = 20
        max_memory_window = 200
        """

        p = Path(path)
        data = tomllib.loads(p.read_text(encoding="utf-8"))

        channels_cfg: Dict[str, ChannelConfig] = {}
        for name, cfg in (data.get("channels") or {}).items():
            channels_cfg[name] = ChannelConfig(
                channel_type=name,
                default_memory_window=cfg.get("default_memory_window", 20),
                max_memory_window=cfg.get("max_memory_window", 200),
                token=cfg.get("token"),
                poll_interval_seconds=float(cfg.get("poll_interval_seconds", 2.0)),
                message_timeout_seconds=float(cfg.get("message_timeout_seconds", 60.0)),
                max_concurrent_conversations=int(
                    cfg.get("max_concurrent_conversations", 10)
                ),
                proxy=cfg.get("proxy"),
                verify_ssl=bool(cfg.get("verify_ssl", True)),
                app_id=cfg.get("app_id"),
                app_secret=cfg.get("app_secret"),
                verification_token=cfg.get("verification_token"),
                listen_host=cfg.get("listen_host"),
                listen_port=cfg.get("listen_port"),
            )

        llm_cfg_data = data.get("llm") or {}
        llm_cfg = None
        if llm_cfg_data:
            llm_cfg = LLMConfig(
                endpoint=llm_cfg_data.get("endpoint"),
                api_key=llm_cfg_data.get("api_key"),
                model=llm_cfg_data.get("model"),
                timeout=float(llm_cfg_data.get("timeout", 10.0)),
            )

        mcp_servers: List[McpServerConfig] = []
        for srv in (data.get("mcp") or {}).get("servers", []):
            srv_id = srv.get("id")
            srv_cmd = srv.get("command")
            if not srv_id or not srv_cmd:
                continue
            mcp_servers.append(McpServerConfig(
                id=srv_id,
                command=srv_cmd if isinstance(srv_cmd, list) else [srv_cmd],
                env=srv.get("env") or {},
            ))

        toml_dir = p.parent
        data_dir_raw = (data.get("guabot") or {}).get("data_dir", ".guabot")
        data_dir = str((toml_dir / data_dir_raw).expanduser().resolve())

        def _resolve_dir(raw: str) -> str:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = toml_dir / path
            return str(path.resolve())

        skills_data = data.get("skills") or {}
        default_dirs_raw: List[str] = skills_data.get("default_dirs", [])
        extension_dirs_raw: List[str] = skills_data.get("extension_dirs", [])
        if not default_dirs_raw and not extension_dirs_raw:
            # 向后兼容：从 data_dir 派生
            default_dirs_raw = [str(Path(data_dir) / "skills")]
        skills_cfg = SkillsConfig(
            default_dirs=[_resolve_dir(d) for d in default_dirs_raw],
            extension_dirs=[_resolve_dir(d) for d in extension_dirs_raw],
        )

        memory_cfg = data.get("memory") or {}
        ttl_seconds = memory_cfg.get("task_state_ttl_seconds")
        if ttl_seconds is None and memory_cfg.get("task_state_ttl_minutes") is not None:
            ttl_seconds = int(memory_cfg.get("task_state_ttl_minutes", 30)) * 60
        if ttl_seconds is None:
            ttl_seconds = 1800

        # 加载上下文压缩配置
        compression_cfg_data = data.get("context_compression") or {}
        compression_cfg = ContextCompressionConfig(
            enabled=bool(compression_cfg_data.get("enabled", True)),
            trigger_threshold=float(compression_cfg_data.get("trigger_threshold", 0.8)),
            target_threshold=float(compression_cfg_data.get("target_threshold", 0.6)),
            keep_recent_turns=int(compression_cfg_data.get("keep_recent_turns", 5)),
            compression_model=compression_cfg_data.get("compression_model", "claude-haiku-4-5"),
            max_summary_tokens=int(compression_cfg_data.get("max_summary_tokens", 100)),
        )

        # 加载 tool 重试配置
        retry_cfg_data = data.get("tool_retry") or {}
        retry_cfg = ToolRetryConfig(
            enabled=bool(retry_cfg_data.get("enabled", True)),
            default_max_retries=int(retry_cfg_data.get("default_max_retries", 3)),
            default_backoff_base=float(retry_cfg_data.get("default_backoff_base", 1.0)),
            max_total_retry_time=float(retry_cfg_data.get("max_total_retry_time", 30.0)),
            retryable_errors=retry_cfg_data.get("retryable_errors", [
                "NetworkError", "TimeoutError", "RateLimitError", "ConnectionError"
            ]),
            non_retryable_errors=retry_cfg_data.get("non_retryable_errors", [
                "AuthenticationError", "InvalidInputError", "PermissionError"
            ]),
        )

        # 加载 skill 超时配置
        timeout_cfg_data = data.get("skill_timeout") or {}
        timeout_cfg = SkillTimeoutConfig(
            enabled=bool(timeout_cfg_data.get("enabled", True)),
            default_timeout=float(timeout_cfg_data.get("default_timeout", 60.0)),
            grace_period=float(timeout_cfg_data.get("grace_period", 5.0)),
        )

        return cls(channels=channels_cfg, llm=llm_cfg, mcp_servers=mcp_servers,
                   data_dir=data_dir,
                   memory_extractor_interval=int(memory_cfg.get("extractor_interval_minutes", 0)),
                   profile_updater_interval=int(memory_cfg.get("profile_interval_minutes", 0)),
                   task_state_ttl_seconds=int(ttl_seconds),
                   skills=skills_cfg,
                   context_compression=compression_cfg,
                   tool_retry=retry_cfg,
                   skill_timeout=timeout_cfg)




@dataclass
class LLMConfig:
    """LLM 相关配置，包括 OpenRouter/OpenAI 等。"""

    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: float = 10.0

    @classmethod
    def from_env(cls, prefix: str = "GUABOT_LLM_") -> "LLMConfig | None":
        """从环境变量加载 LLM 配置。

        约定使用前缀 + 字段名的大写形式，例如：

        - GUABOT_LLM_ENDPOINT
        - GUABOT_LLM_API_KEY
        - GUABOT_LLM_MODEL
        - GUABOT_LLM_TIMEOUT

        如果三者（endpoint/api_key/model）均缺失，则返回 None，表示环境变量未配置。
        """

        endpoint = os.getenv(f"{prefix}ENDPOINT")
        api_key = os.getenv(f"{prefix}API_KEY")
        model = os.getenv(f"{prefix}MODEL")
        timeout_raw = os.getenv(f"{prefix}TIMEOUT", "10.0")
        try:
            timeout = float(timeout_raw)
        except ValueError:
            timeout = 10.0

        if not (endpoint or api_key or model):
            return None

        return cls(endpoint=endpoint, api_key=api_key, model=model, timeout=timeout)
