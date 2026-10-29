"""工具执行器：负责工具查找、参数校验、异步执行及异常处理。"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from myagent.core.errors import ToolError
from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class ToolExecutor:
    """管理当前 Agent 的可执行工具，统一处理工具调用。"""

    def __init__(self, tools: list[BaseTool]) -> None:
        """接收当前 Agent 的工具集合，建立名称与工具实例的映射。"""
        if not isinstance(tools, list):
            raise ToolError("tools 必须是工具实例列表")

        self._tools: dict[str, BaseTool] = {}

        for tool in tools:
            if not isinstance(tool, BaseTool):
                raise ToolError("工具集合中存在非 BaseTool 实例")
            if tool.name in self._tools:
                raise ToolError(f"工具名称重复：{tool.name}")
            self._tools[tool.name] = tool

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """统一构造工具执行失败结果。"""
        return ToolResult(
            success=False,
            content=message,
            error=ToolErrorInfo(code=code, message=message)
        )

    async def execute(self, name: str, arguments: dict[str, Any] | str) -> ToolResult:
        """查找工具、解析并校验参数，执行后返回统一结果。"""

        # 1. 查找当前 Agent 允许使用的工具
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return self._failure("TOOL_NOT_FOUND", f"工具不存在或不可用：{name}")

        # 2. 解析模型返回的 JSON 字符串
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return self._failure("INVALID_ARGUMENTS", "工具参数不是合法的 JSON")

        if not isinstance(arguments, dict):
            return self._failure("INVALID_ARGUMENTS", "工具参数必须是 JSON 对象")

        # 3. 使用工具的 Pydantic 模型校验参数
        try:
            validated = tool.args_schema.model_validate(arguments)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(map(str, error['loc'])) or 'arguments'}: {error['msg']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
            return self._failure("INVALID_ARGUMENTS", f"工具参数校验失败：{details}")

        # 4. 执行工具，统一处理执行异常
        try:
            result = await tool.execute(validated.model_dump())

            if not isinstance(result, ToolResult):
                raise TypeError(f"{name}.execute() 必须返回 ToolResult")

            return result  # 包括工具主动返回的失败结果，不重复包装

        except Exception:
            logger.exception("工具执行异常：%s", name)
            return self._failure("EXECUTION_ERROR", "工具执行过程中发生异常")