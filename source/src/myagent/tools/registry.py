"""
工具注册表：负责从 YAML 动态加载、注册和查找系统工具。
"""

from importlib import import_module
from pathlib import Path

import yaml

from myagent.core.errors import ToolError
from myagent.tools.base_tool import BaseTool


class ToolRegistry:
    """
    系统工具注册表，统一管理工具名称与实例。
    """

    def __init__(self) -> None:
        """
        初始化空工具注册表。
        """
        self._tools: dict[str, BaseTool] = {}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ToolRegistry":
        """
        从 YAML 工具清单动态加载并注册所有工具。
        """
        path = Path(path)

        # 读取工具清单，要求格式为 tools: [工具类导入路径, ...]
        try:
            with path.open("r", encoding="utf-8") as file:
                config = yaml.safe_load(file)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ToolError(f"工具清单读取或解析失败：{path}") from exc

        if not isinstance(config, dict) or set(config) != {"tools"}:
            raise ToolError(f"工具清单必须包含且仅包含 tools 字段：{path}")

        tool_paths = config["tools"]
        if not isinstance(tool_paths, list):
            raise ToolError("tools 必须是工具类导入路径组成的列表")

        registry = cls()

        for class_path in tool_paths:
            if not isinstance(class_path, str) or not class_path.strip() or "." not in class_path:
                raise ToolError(f"无效的工具类导入路径：{class_path!r}")

            # 将完整类路径拆分为模块路径和类名
            module_path, class_name = class_path.rsplit(".", 1)

            try:
                tool_class = getattr(import_module(module_path), class_name)
            except (ImportError, AttributeError) as exc:
                raise ToolError(f"无法加载工具类：{class_path}") from exc

            # 所有工具必须继承 BaseTool
            if not isinstance(tool_class, type) or not issubclass(tool_class, BaseTool):
                raise ToolError(f"{class_path} 必须是 BaseTool 的子类")

            # 工具类必须支持无参数实例化，具体参数和元数据由工具自身定义
            try:
                tool = tool_class()
            except Exception as exc:
                raise ToolError(f"工具实例化失败：{class_path}") from exc

            registry.register(tool)

        return registry

    def register(self, tool: BaseTool) -> None:
        """
        注册工具，禁止重复名称和非 BaseTool 实例。
        """
        if not isinstance(tool, BaseTool):
            raise ToolError("注册对象必须是 BaseTool 实例")

        if tool.name in self._tools:
            raise ToolError(f"工具名称重复：{tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """
        根据名称获取工具，不存在时抛出 KeyError。
        """
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"工具未注册：{name}") from None

    def list_names(self) -> list[str]:
        """
        返回所有已注册工具名称，保持注册顺序。
        """
        return list(self._tools)

    def get_descriptions(self) -> str:
        """返回工具名称和描述，用于 SystemPrompt。"""
        return "\n".join(f"- {tool.name}: {tool.description}" for tool in self._tools.values())

    def get_definitions(self, protocol: str) -> list[dict[str, Any]]:
        """返回当前暴露工具的协议适配定义，用于 Context.tools。"""
        ...