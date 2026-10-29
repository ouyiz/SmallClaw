"""文件内容搜索工具：支持关键词和正则表达式搜索。"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class GrepArgs(BaseModel):
    """文件内容搜索工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    pattern: str = Field(min_length=1, description="需要搜索的关键词或正则表达式。")
    path: str = Field(default=".", min_length=1, description="搜索路径，可以是文件或目录，支持绝对路径和相对于当前进程工作目录的相对路径。")
    regex: bool = Field(default=False, description="是否将 pattern 作为正则表达式，默认按普通文本精确匹配。")
    case_sensitive: bool = Field(default=True, description="是否区分大小写，默认区分。")
    recursive: bool = Field(default=True, description="搜索目录时是否递归查找子目录，默认递归。")
    max_results: int = Field(default=100, ge=1, le=1000, description="最多返回的匹配行数，默认 100，最大 1000。")


class GrepTool(BaseTool):
    """在指定文件或目录中搜索文本内容。"""

    name = "grep"
    description = (
        "在 UTF-8 文本文件中逐行搜索关键词或正则表达式，适用于定位代码、变量和文档内容。"
        "支持单文件、目录递归搜索及大小写控制，自动跳过二进制文件。"
        "不修改文件，返回匹配的文件路径、行号和文本内容。"
        "默认最多返回 100 条匹配结果，每条文本最多显示 500 个字符。"
    )
    args_schema = GrepArgs

    _MAX_LINE_LENGTH = 500

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造文件搜索失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    def _search(self, arguments: dict[str, Any]) -> ToolResult:
        """同步搜索文件内容，由 execute() 放入工作线程执行。"""
        path = Path(arguments["path"]).resolve()
        max_results = arguments["max_results"]
        matches = []
        truncated = False
        skipped_files = 0

        # 1. 检查搜索路径
        if not path.exists():
            return self._failure("PATH_NOT_FOUND", f"搜索路径不存在：{arguments['path']}")
        if not path.is_file() and not path.is_dir():
            return self._failure("INVALID_PATH", "搜索路径必须是文件或目录")

        # 2. 编译匹配规则；普通关键词使用 re.escape() 避免被解释为正则表达式
        flags = 0 if arguments["case_sensitive"] else re.IGNORECASE
        expression = arguments["pattern"] if arguments["regex"] else re.escape(arguments["pattern"])
        try:
            matcher = re.compile(expression, flags)
        except re.error as exc:
            return self._failure("INVALID_PATTERN", f"正则表达式不合法：{exc}")

        # 3. 根据路径类型确定需要搜索的文件
        single_file = path.is_file()
        files = [path] if single_file else (path.rglob("*") if arguments["recursive"] else path.iterdir())

        try:
            for file_path in files:
                if not file_path.is_file():
                    continue

                previous_count = len(matches)

                try:
                    # 检测常见二进制文件，避免将其作为普通文本搜索
                    with file_path.open("rb") as file:
                        if b"\x00" in file.read(4096):
                            if single_file:
                                return self._failure("BINARY_FILE", "指定文件不是普通文本文件")
                            skipped_files += 1
                            continue

                    # 逐行读取，避免一次性将整个文件加载到内存
                    with file_path.open("r", encoding="utf-8") as file:
                        for line_no, line in enumerate(file, start=1):
                            if not matcher.search(line):
                                continue

                            if len(matches) >= max_results:
                                truncated = True
                                break

                            text = line.rstrip("\r\n")
                            if len(text) > self._MAX_LINE_LENGTH:
                                text = text[:self._MAX_LINE_LENGTH] + "... [行内容已截断]"

                            matches.append({
                                "path": str(file_path),
                                "line": line_no,
                                "text": text,
                            })

                except UnicodeDecodeError:
                    if single_file:
                        return self._failure("DECODE_ERROR", "文件不是有效的 UTF-8 文本")
                    # 文件编码异常时丢弃该文件的部分结果，继续搜索其他文件
                    del matches[previous_count:]
                    skipped_files += 1

                if truncated:
                    break

        except PermissionError:
            return self._failure("PERMISSION_DENIED", f"没有搜索路径的读取权限：{arguments['path']}")
        except OSError:
            logger.exception("文件内容搜索异常：%s", path)
            return self._failure("GREP_ERROR", "文件内容搜索过程中发生系统错误")

        # 4. 返回带路径和行号的匹配结果
        content = "\n".join(f"{item['path']}:{item['line']}: {item['text']}" for item in matches)
        if not content:
            content = "未找到匹配内容。"
        if truncated:
            content += f"\n[结果已截断，最多返回 {max_results} 条，请缩小搜索范围]"
        if skipped_files:
            content += f"\n[已跳过 {skipped_files} 个二进制或非 UTF-8 文件]"

        return ToolResult(
            success=True,
            content=content,
            data={
                "path": arguments["path"],
                "pattern": arguments["pattern"],
                "matches": matches,
                "count": len(matches),
                "truncated": truncated,
                "skipped_files": skipped_files,
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行文件内容搜索，参数由 ToolExecutor 提前校验。"""
        return await asyncio.to_thread(self._search, arguments)