from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import os
try:  # py3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 兼容本地 py3.10 测试环境
    import tomli as tomllib


@dataclass
class ChannelConfig:
    """单个 IM 渠道配置。

    这里只描述与脚手架强相关的最小字段，便于后续扩展。
    """

    channel_type: str
    default_memory_window: int = 20
    max_memory_window: int = 200


@dataclass
class AppConfig:
    """脚手架运行时配置（简化版）。"""

    channels: Dict[str, ChannelConfig] = field(default_factory=dict)
    llm: Optional["LLMConfig"] = None

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

        return cls(channels=channels_cfg, llm=llm_cfg)


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
