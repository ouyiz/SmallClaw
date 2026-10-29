"""工具抽象基类，统一工具定义与执行接口。"""

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from myagent.core.errors import ToolError
from myagent.tools.schemas import ToolResult


class BaseTool(ABC):
    """
    所有工具的抽象基类。
    """

    # 工具元数据，由具体工具子类定义
    name: ClassVar[str]
    description: ClassVar[str]
    args_schema: ClassVar[type[BaseModel]]

    # 工具名称统一使用 snake_case，以小写字母开头
    _NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    def __init__(self) -> None:
        """
        初始化工具并检查元数据是否合法。
        """
        self._validate_definition()

    def _validate_definition(self) -> None:
        """
        校验工具名称、描述和参数模型，不检查名称唯一性。
        """
        name = getattr(self, "name", None)
        if not isinstance(name, str) or not self._NAME_PATTERN.fullmatch(name):
            raise ToolError(f"{type(self).__name__}: 工具名称必须使用 snake_case，并以小写字母开头")

        description = getattr(self, "description", None)
        if not isinstance(description, str) or not description.strip():
            raise ToolError(f"{name}: 工具描述不能为空")

        schema = getattr(self, "args_schema", None)
        if not isinstance(schema, type) or not issubclass(schema, BaseModel) or schema is BaseModel:
            raise ToolError(f"{name}: args_schema 必须是 Pydantic BaseModel 的子类")

    def get_definition(self) -> dict[str, Any]:
        """
        生成统一工具定义，由 LLMClient 转换为具体模型协议格式。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema.model_json_schema(),
        }

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """
        执行工具并返回统一结果，arguments 由 ToolExecutor 提前校验。
        """
        ...