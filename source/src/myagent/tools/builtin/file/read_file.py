"""读取文件工具：支持 UTF-8 文本读取及指定行号范围。"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class ReadFileArgs(BaseModel):
    """读取文件工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="需要读取的文件路径，支持绝对路径和相对于当前进程工作目录的相对路径。")
    start_line: int = Field(default=1, ge=1, description="开始读取的行号，从 1 开始。")
    end_line: int | None = Field(default=None, ge=1, description="结束行号（包含），不填写则读取到文件末尾或输出上限。")

    @model_validator(mode="after")
    def validate_range(self) -> "ReadFileArgs":
        """结束行号不能小于开始行号。"""
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError("end_line 不能小于 start_line")
        return self


class ReadFileTool(BaseTool):
    """读取指定路径的文本文件。"""

    name = "read_file"
    description = (
        "读取指定路径的 UTF-8 文本文件，适用于查看代码和文档。"
        "支持绝对路径、相对路径及指定起止行号，每次最多返回 200 行，结果包含行号。"
        "不会修改文件，不限制读取目录。"
    )
    args_schema = ReadFileArgs

    _MAX_LINES = 200

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造文件读取失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    def _read(self, arguments: dict[str, Any]) -> ToolResult:
        """同步读取文件，由 execute() 放入工作线程执行。"""
        path = Path(arguments["path"]).resolve()

        start_line = arguments["start_line"]
        end_line = arguments["end_line"]
        lines = []
        truncated = False

        try:
            with path.open("r", encoding="utf-8") as file:
                for line_no, line in enumerate(file, start=1):
                    if line_no < start_line:
                        continue
                    if end_line is not None and line_no > end_line:
                        break
                    if len(lines) >= self._MAX_LINES:
                        truncated = True
                        break
                    lines.append(f"{line_no}: {line.rstrip(chr(10)).rstrip(chr(13))}")

        except FileNotFoundError:
            return self._failure("FILE_NOT_FOUND", f"文件不存在：{arguments['path']}")
        except IsADirectoryError:
            return self._failure("NOT_A_FILE", f"指定路径是目录而不是文件：{arguments['path']}")
        except PermissionError:
            return self._failure("PERMISSION_DENIED", f"没有文件读取权限：{arguments['path']}")
        except UnicodeDecodeError:
            return self._failure("DECODE_ERROR", "文件不是有效的 UTF-8 文本")
        except OSError:
            logger.exception("文件读取异常：%s", path)
            return self._failure("READ_ERROR", "文件读取过程中发生系统错误")

        # 返回带行号的文本，超出行数限制时提示分段读取
        content = "\n".join(lines) if lines else "指定行号范围内没有内容。"
        if truncated:
            content += "\n[输出已截断，请调整 start_line 继续读取]"

        return ToolResult(
            success=True,
            content=content,
            data={
                "path": arguments["path"],
                "start_line": start_line,
                "end_line": start_line + len(lines) - 1 if lines else None,
                "truncated": truncated,
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行文件读取，参数由 ToolExecutor 提前校验。"""
        return await asyncio.to_thread(self._read, arguments)