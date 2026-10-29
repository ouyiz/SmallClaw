"""文件查找工具：通过 Glob 通配符匹配文件路径。"""

import asyncio
import glob
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class GlobArgs(BaseModel):
    """文件查找工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(min_length=1, description="文件匹配模式，支持绝对路径、相对路径及 *、?、[]、** 通配符。例如 projects/**/*.py。")
    max_results: int = Field(default=100, ge=1, le=1000, description="最多返回的文件数量，默认 100，最大 1000。")


class GlobTool(BaseTool):
    """使用 Glob 通配符查找文件。"""

    name = "glob"
    description = (
        "根据 Glob 通配符查找文件路径，适用于按名称、扩展名或目录结构定位文件。"
        "支持绝对路径、相对路径及 ** 递归搜索，仅返回文件，不读取文件内容。"
        "默认最多返回 100 个结果，结果按路径排序，超出数量限制时提示截断。"
    )
    args_schema = GlobArgs

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造文件查找失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    def _search(self, arguments: dict[str, Any]) -> ToolResult:
        """同步搜索文件，由 execute() 放入工作线程执行。"""
        pattern = arguments["pattern"]
        max_results = arguments["max_results"]
        matches = []
        seen = set()
        truncated = False

        try:
            # 逐个遍历匹配路径，只保留文件并去除重复结果
            for filename in glob.iglob(pattern, recursive=True):
                path = Path(filename)
                if not path.is_file():
                    continue

                filename = path.as_posix()
                if filename in seen:
                    continue

                if len(matches) >= max_results:
                    truncated = True
                    break

                matches.append(filename)
                seen.add(filename)

        except OSError:
            logger.exception("文件查找异常：%s", pattern)
            return self._failure("GLOB_ERROR", "文件查找过程中发生系统错误")

        # 排序并整理返回内容
        matches.sort()
        content = "\n".join(matches) if matches else "未找到匹配的文件。"
        if truncated:
            content += f"\n[结果已截断，最多返回 {max_results} 个文件，请缩小搜索范围]"

        return ToolResult(
            success=True,
            content=content,
            data={
                "pattern": pattern,
                "matches": matches,
                "count": len(matches),
                "truncated": truncated,
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行文件查找，参数由 ToolExecutor 提前校验。"""
        return await asyncio.to_thread(self._search, arguments)