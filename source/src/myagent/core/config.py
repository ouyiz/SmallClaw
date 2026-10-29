"""
Agent 配置管理：负责 YAML 加载、配置校验及扩展参数存储。
"""

import keyword
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from myagent.core.errors import ConfigError


class AgentConfig(BaseModel):
    """
    Agent 通用配置，支持动态加载自定义 Agent 和 Loop。
    """

    model_config = ConfigDict(
        extra="forbid",             # 禁止未定义的顶层配置字段
        validate_assignment=True,  # 修改成员属性时重新校验
        str_strip_whitespace=True,  # 自动去除字符串首尾空格
    )

    # Agent 基本信息
    name: str = Field(min_length=1)
    agent_class: str = "myagent.core.my_agent.MyAgent"
    loop_class: str = "myagent.core.loop.AgentLoop"

    # 模型与提示词
    model: dict[str, Any]
    system_prompt: str = Field(min_length=1)

    # Agent 能力配置
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    memory: dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "files": []})
    hooks: list[str] = Field(default_factory=list)

    # 运行控制
    max_steps: int = Field(default=20, ge=1, strict=True)
    max_tool_calls: int = Field(default=30, ge=0, strict=True)
    max_context_tokens: int = Field(default=32000, ge=1, strict=True)
    auto_compact: bool = True
    workspace: str = Field(default="data/workspace/", min_length=1)

    # 扩展配置，由具体 Agent 和 Loop 负责进一步校验
    agent_options: dict[str, Any] = Field(default_factory=dict)
    loop_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_class", "loop_class")
    @classmethod
    def validate_class_path(cls, value: str) -> str:
        """
        校验 Python 类导入路径的格式，不在此处执行动态导入。
        """
        parts = value.split(".")
        if len(parts) < 2 or any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
            raise ValueError(f"无效的 Python 类导入路径：{value}")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: dict[str, Any]) -> dict[str, Any]:
        """
        校验模型必要参数，保留不同模型的扩展配置。
        """
        for key in ("provider", "protocol", "model_name"):
            if not isinstance(value.get(key), str) or not value[key].strip():
                raise ValueError(f"模型配置缺少有效的 {key}")

        if value["protocol"] not in ("openai", "anthropic"):
            raise ValueError(f"不支持的模型协议：{value['protocol']}")

        # API Key 存储在环境变量中，配置文件只记录变量名称
        key_env = value.get("api_key_env")
        if key_env is not None and (not isinstance(key_env, str) or not key_env.strip()):
            raise ValueError("api_key_env 必须是非空字符串或 null")

        base_url = value.get("base_url")
        if base_url is not None and (not isinstance(base_url, str) or not base_url.strip()):
            raise ValueError("base_url 必须是非空字符串或 null")

        # 校验常用模型参数；协议特有参数由 LLMClient 进一步处理
        for key in ("max_tokens", "max_completion_tokens"):
            if key in value and (type(value[key]) is not int or value[key] <= 0):
                raise ValueError(f"{key} 必须是正整数")

        if "max_retries" in value and (type(value["max_retries"]) is not int or value["max_retries"] < 0):
            raise ValueError("max_retries 必须是非负整数")

        return value

    @field_validator("tools", "skills", "hooks")
    @classmethod
    def validate_names(cls, value: list[str]) -> list[str]:
        """
        校验工具、技能和 Hook 名称，禁止空名称和重复配置。
        """
        if any(not name.strip() for name in value):
            raise ValueError("配置列表中不能包含空名称")
        if len(value) != len(set(value)):
            raise ValueError("配置列表中存在重复名称")
        return value

    @field_validator("memory")
    @classmethod
    def validate_memory(cls, value: dict[str, Any]) -> dict[str, Any]:
        """
        校验记忆开关及预加载文件列表。
        """
        if not isinstance(value.get("enabled", False), bool):
            raise ValueError("memory.enabled 必须是布尔值")

        files = value.get("files", [])
        if not isinstance(files, list) or any(not isinstance(f, str) or not f.strip() for f in files):
            raise ValueError("memory.files 必须是非空字符串组成的列表")
        return value

    @classmethod
    def from_yaml(cls, path: str | Path) -> "AgentConfig":
        """
        从 YAML 文件读取配置，并使用 Pydantic 自动校验。
        """
        path = Path(path)

        try:
            with path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ConfigError(f"Agent 配置文件读取或解析失败：{path}") from exc

        if not isinstance(data, dict):
            raise ConfigError(f"Agent 配置必须是 YAML 对象：{path}")

        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(f"Agent 配置校验失败：{path}") from exc