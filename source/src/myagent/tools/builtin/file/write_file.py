"""写入文件工具：支持创建文件、UTF-8 文本写入及覆盖控制。"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class WriteFileArgs(BaseModel):
    """写入文件工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="需要写入的文件路径，支持绝对路径和相对于当前进程工作目录的相对路径。")
    content: str = Field(description="需要写入的 UTF-8 文本内容，允许空字符串。")
    overwrite: bool = Field(default=False, description="是否覆盖已有文件，默认不覆盖；文件已存在时返回错误。")
    create_parents: bool = Field(default=False, description="父目录不存在时是否自动创建，默认不创建。")


class WriteFileTool(BaseTool):
    """创建或写入指定路径的文本文件。"""

    name = "write_file"
    description = (
        "创建文件并写入 UTF-8 文本，适用于生成代码、文档和其他文本文件。"
        "支持绝对路径和相对路径，可选择覆盖已有文件或自动创建父目录。"
        "默认不覆盖已有文件，覆盖时会替换文件的全部内容，而非局部修改。"
        "返回文件路径和写入的字符数。"
    )
    args_schema = WriteFileArgs

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造文件写入失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    def _write(self, arguments: dict[str, Any]) -> ToolResult:
        """同步写入文件，由 execute() 放入工作线程执行。"""
        path = Path(arguments["path"]).resolve()
        content = arguments["content"]

        try:
            # 按需创建父目录
            if arguments["create_parents"]:
                path.parent.mkdir(parents=True, exist_ok=True)

            # x：文件已存在则拒绝写入；w：允许覆盖已有文件
            mode = "w" if arguments["overwrite"] else "x"
            with path.open(mode, encoding="utf-8", newline="\n") as file:
                file.write(content)

        except FileExistsError:
            return self._failure("FILE_EXISTS", f"文件已存在，如需覆盖请设置 overwrite=true：{arguments['path']}")
        except FileNotFoundError:
            return self._failure("PARENT_NOT_FOUND", f"父目录不存在：{arguments['path']}")
        except IsADirectoryError:
            return self._failure("NOT_A_FILE", f"指定路径是目录而不是文件：{arguments['path']}")
        except PermissionError:
            return self._failure("PERMISSION_DENIED", f"没有文件写入权限：{arguments['path']}")
        except UnicodeEncodeError:
            return self._failure("ENCODE_ERROR", "文本内容无法使用 UTF-8 编码")
        except OSError:
            logger.exception("文件写入异常：%s", path)
            return self._failure("WRITE_ERROR", "文件写入过程中发生系统错误")

        return ToolResult(
            success=True,
            content=f"文件写入成功：{arguments['path']}，共写入 {len(content)} 个字符。",
            data={
                "path": arguments["path"],
                "characters_written": len(content),
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行文件写入，参数由 ToolExecutor 提前校验。"""
        return await asyncio.to_thread(self._write, arguments)