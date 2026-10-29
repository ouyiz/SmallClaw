"""编辑文件工具：通过精确匹配原文修改 UTF-8 文本文件。"""

import asyncio
import logging
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class EditFileArgs(BaseModel):
    """编辑文件工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, description="需要编辑的文件路径，支持绝对路径和相对于当前进程工作目录的相对路径。")
    old_text: str = Field(min_length=1, description="需要被替换的原始文本，必须与文件中的内容完全一致，包括空格和换行。")
    new_text: str = Field(description="替换后的文本，允许空字符串，表示删除匹配内容。")
    replace_all: bool = Field(default=False, description="是否替换全部匹配内容，默认只允许原文唯一匹配。")


class EditFileTool(BaseTool):
    """精确替换指定文件中的文本内容。"""

    name = "edit_file"
    description = (
        "精确替换 UTF-8 文本文件中的指定内容，适用于修改代码和文档。"
        "支持绝对路径和相对路径，必须提供完全匹配的原文及替换文本。"
        "默认要求原文在文件中只出现一次，多个匹配需设置 replace_all=true。"
        "保留未匹配的内容，返回实际替换次数。"
    )
    args_schema = EditFileArgs

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造文件编辑失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    def _edit(self, arguments: dict[str, Any]) -> ToolResult:
        """同步编辑文件，由 execute() 放入工作线程执行。"""
        path = Path(arguments["path"]).resolve()
        old_text = arguments["old_text"]
        new_text = arguments["new_text"]
        replace_all = arguments["replace_all"]
        temp_path = None

        try:
            # 读取原文，保留原始换行格式和文件权限
            with path.open("r", encoding="utf-8", newline="") as file:
                original = file.read()
                file_mode = stat.S_IMODE(os.fstat(file.fileno()).st_mode)

            # 精确匹配，默认拒绝存在多个匹配位置的情况
            count = original.count(old_text)
            if count == 0:
                return self._failure("TEXT_NOT_FOUND", "文件中未找到需要替换的原文")
            if count > 1 and not replace_all:
                return self._failure("MULTIPLE_MATCHES", f"原文出现 {count} 次，请提供更精确的原文或设置 replace_all=true")
            if old_text == new_text:
                return self._failure("NO_CHANGES", "替换前后的文本相同，文件未发生修改")

            updated = original.replace(old_text, new_text, -1 if replace_all else 1)
            replacements = count if replace_all else 1

            # 先写入同目录的临时文件，成功后再替换原文件，避免直接截断原文件
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as file:
                temp_path = Path(file.name)
                file.write(updated)

            os.chmod(temp_path, file_mode)
            os.replace(temp_path, path)

        except FileNotFoundError:
            return self._failure("FILE_NOT_FOUND", f"文件不存在：{arguments['path']}")
        except IsADirectoryError:
            return self._failure("NOT_A_FILE", f"指定路径是目录而不是文件：{arguments['path']}")
        except PermissionError:
            return self._failure("PERMISSION_DENIED", f"没有文件读写权限：{arguments['path']}")
        except UnicodeDecodeError:
            return self._failure("DECODE_ERROR", "文件不是有效的 UTF-8 文本")
        except UnicodeEncodeError:
            return self._failure("ENCODE_ERROR", "替换内容无法使用 UTF-8 编码")
        except OSError:
            logger.exception("文件编辑异常：%s", path)
            return self._failure("EDIT_ERROR", "文件编辑过程中发生系统错误")
        finally:
            # 编辑失败时清理临时文件；成功后原临时路径已被替换
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("临时文件清理失败：%s", temp_path)

        return ToolResult(
            success=True,
            content=f"文件编辑成功：{arguments['path']}，共替换 {replacements} 处内容。",
            data={
                "path": arguments["path"],
                "replacements": replacements,
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行文件编辑，参数由 ToolExecutor 提前校验。"""
        return await asyncio.to_thread(self._edit, arguments)