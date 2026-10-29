"""SystemPrompt 构建器：生成固定区块并管理插件提示词扩展。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from myagent.core.config import AgentConfig
from myagent.core.run_context import RunContext
from myagent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from myagent.memory.manager import MemoryManager
    from myagent.skills.loader import SkillLoader


class PromptBuilder:
    """按照固定顺序构建 Agent 的系统提示词。"""

    _SECTION_TITLES = (
        "Identity",
        "Agent Instructions",
        "Tool Instructions",
        "Skills",
        "Memory Instructions",
        "Environment",
        "Output Instructions",
        "Extensions",
    )

    _IDENTITY_PROMPT = (
        "你是 myAgent 框架运行的智能 Agent。你应遵循系统提示词中的约束，"
        "围绕用户目标进行可靠、透明且可验证的工作。"
    )

    _TOOL_USAGE_RULES = (
        "工具使用规则：\n"
        "- 仅调用下列已提供的工具，不得虚构工具或参数。\n"
        "- 调用前确认工具适用于当前任务，并严格遵守其参数定义。\n"
        "- 根据工具返回的实际结果继续工作，不得声称未执行的操作已经完成。\n"
        "- 工具调用失败时，应根据错误信息调整方案；不得无意义地重复调用。"
    )

    _DEFAULT_OUTPUT_INSTRUCTIONS = (
        "输出应准确、清晰且直接回应用户目标。区分已验证的事实、合理推断与不确定信息；"
        "不得伪造执行结果、引用或来源。"
    )

    def __init__(
        self,
        config: AgentConfig,
        tool_registry: ToolRegistry,
        skill_loader: SkillLoader | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> None:
        """保存组件依赖并初始化空的插件扩展注册表。"""
        if not isinstance(config, AgentConfig):
            raise TypeError("config 必须是 AgentConfig 实例")
        if not isinstance(tool_registry, ToolRegistry):
            raise TypeError("tool_registry 必须是 ToolRegistry 实例")

        self._config = config
        self._tool_registry = tool_registry
        self._skill_loader = skill_loader
        self._memory_manager = memory_manager
        self._extensions: dict[str, dict[str, Any]] = {}

    def register_extension(
        self,
        name: str,
        builder: Callable[[RunContext], str],
        priority: int = 100,
        *,
        enabled: bool = True,
    ) -> None:
        """注册扩展提示词生成函数；扩展名称必须唯一。"""
        normalized_name = self._validate_extension_name(name)
        if not callable(builder):
            raise TypeError("builder 必须是可调用对象")
        self._validate_priority(priority)
        if not isinstance(enabled, bool):
            raise TypeError("enabled 必须是 bool")
        if normalized_name in self._extensions:
            raise ValueError(f"扩展已注册：{normalized_name}")

        self._extensions[normalized_name] = {
            "builder": builder,
            "priority": priority,
            "enabled": enabled,
        }

    def unregister_extension(self, name: str) -> None:
        """移除一个已注册扩展。"""
        normalized_name = self._validate_extension_name(name)
        try:
            del self._extensions[normalized_name]
        except KeyError:
            raise KeyError(f"扩展未注册：{normalized_name}") from None

    def set_extension_enabled(self, name: str, enabled: bool) -> None:
        """设置扩展是否参与后续 SystemPrompt 构建。"""
        normalized_name = self._validate_extension_name(name)
        if not isinstance(enabled, bool):
            raise TypeError("enabled 必须是 bool")
        extension = self._get_extension(normalized_name)
        extension["enabled"] = enabled

    def set_extension_priority(self, name: str, priority: int) -> None:
        """更新扩展在 Extensions 区块内的排序优先级。"""
        normalized_name = self._validate_extension_name(name)
        self._validate_priority(priority)
        extension = self._get_extension(normalized_name)
        extension["priority"] = priority

    def build(self, run_context: RunContext) -> str:
        """按照固定的 8 个 Section 顺序组装系统提示词。"""
        if not isinstance(run_context, RunContext):
            raise TypeError("run_context 必须是 RunContext 实例")

        contents = (
            self._build_identity(),
            self._build_agent_instructions(),
            self._build_tool_instructions(),
            self._build_skills(),
            self._build_memory_instructions(),
            self._build_environment(run_context),
            self._build_output_instructions(),
            self._build_extensions(run_context),
        )

        sections = [
            self._format_section(title, content)
            for title, content in zip(self._SECTION_TITLES, contents, strict=True)
            if content.strip()
        ]
        return "\n\n".join(sections)

    def _build_identity(self) -> str:
        """生成框架级身份说明。"""
        return self._IDENTITY_PROMPT

    def _build_agent_instructions(self) -> str:
        """读取当前 Agent 的专属提示词。"""
        return self._config.system_prompt.strip()

    def _build_tool_instructions(self) -> str:
        """生成工具列表与工具使用规则，不包含 JSON Schema。"""
        if not self._config.tools:
            return ""

        descriptions = "\n".join(
            f"- {tool.name}: {tool.description}"
            for tool in (
                self._tool_registry.get(name) for name in self._config.tools
            )
        )
        return f"当前可用工具：\n{descriptions}\n\n{self._TOOL_USAGE_RULES}"

    def _build_skills(self) -> str:
        """生成当前 Agent 可用 Skill 的简介。"""
        if self._skill_loader is None or not self._config.skills:
            return ""

        descriptions = self._skill_loader.get_descriptions(self._config.skills)
        return self._require_text(descriptions, "SkillLoader.get_descriptions()").strip()

    def _build_memory_instructions(self) -> str:
        """根据记忆配置生成记忆使用说明。"""
        memory_config = self._config.memory
        if not memory_config.get("enabled", False):
            return ""

        parts = [
            "长期记忆功能已启用。仅在与当前任务相关时使用记忆；不得把推断当作已存储事实。",
            "写入记忆时应保存稳定、可复用的信息，并避免记录密钥、令牌等敏感数据。",
        ]

        files = memory_config.get("files", [])
        if files:
            parts.append("配置的记忆文件：\n" + "\n".join(f"- {path}" for path in files))

        if self._memory_manager is not None:
            manager_instructions = self._memory_manager.get_instructions()
            manager_text = self._require_text(
                manager_instructions,
                "MemoryManager.get_instructions()",
            ).strip()
            if manager_text:
                parts.append(manager_text)

        return "\n\n".join(parts)

    def _build_environment(self, run_context: RunContext) -> str:
        """生成本次 Run 的实时环境信息。"""
        return (
            f"- Working directory: {run_context.cwd}\n"
            f"- Session ID: {run_context.session_id}\n"
            f"- Run ID: {run_context.run_id}\n"
            f"- Current step count: {run_context.step_count}\n"
            f"- Current tool call count: {run_context.tool_call_count}"
        )

    def _build_output_instructions(self) -> str:
        """合并框架默认规则和 Agent 专属输出规则。"""
        parts = [self._DEFAULT_OUTPUT_INSTRUCTIONS]
        custom = self._config.agent_options.get("output_instructions")

        if custom is None:
            return parts[0]
        if isinstance(custom, str):
            custom_text = custom.strip()
        elif isinstance(custom, list) and all(isinstance(item, str) for item in custom):
            custom_text = "\n".join(
                f"- {item.strip()}" for item in custom if item.strip()
            )
        else:
            raise TypeError(
                "agent_options.output_instructions 必须是字符串或字符串列表"
            )

        if custom_text:
            parts.append(custom_text)
        return "\n\n".join(parts)

    def _build_extensions(self, run_context: RunContext) -> str:
        """按优先级稳定排序并生成所有已启用扩展。"""
        enabled_extensions = (
            (name, extension)
            for name, extension in self._extensions.items()
            if extension["enabled"]
        )
        ordered_extensions = sorted(
            enabled_extensions,
            key=lambda item: item[1]["priority"],
        )

        contents: list[str] = []
        for name, extension in ordered_extensions:
            builder = extension["builder"]
            try:
                content = builder(run_context)
            except Exception as exc:
                raise RuntimeError(f"扩展提示词生成失败：{name}") from exc

            text = self._require_text(content, f"扩展 {name!r} 的 builder 返回值").strip()
            if text:
                contents.append(f"### {name}\n\n{text}")

        return "\n\n".join(contents)

    def _get_extension(self, name: str) -> dict[str, Any]:
        """获取扩展注册信息，并统一处理未注册错误。"""
        try:
            return self._extensions[name]
        except KeyError:
            raise KeyError(f"扩展未注册：{name}") from None

    @staticmethod
    def _format_section(title: str, content: str) -> str:
        """将非空内容格式化为统一的 Markdown Section。"""
        return f"## {title}\n\n{content.strip()}"

    @staticmethod
    def _validate_extension_name(name: str) -> str:
        """校验并规范化扩展名称。"""
        if not isinstance(name, str):
            raise TypeError("扩展名称必须是字符串")
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("扩展名称不能为空")
        if "\n" in normalized_name or "\r" in normalized_name:
            raise ValueError("扩展名称不能包含换行符")
        return normalized_name

    @staticmethod
    def _validate_priority(priority: int) -> None:
        """校验扩展优先级，拒绝 bool 这一 int 子类型。"""
        if type(priority) is not int:
            raise TypeError("priority 必须是整数")

    @staticmethod
    def _require_text(value: object, source: str) -> str:
        """确保各内容提供方遵守字符串返回契约。"""
        if not isinstance(value, str):
            raise TypeError(f"{source} 必须返回字符串")
        return value
