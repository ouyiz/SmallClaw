"""Shell 工具：异步执行命令，返回退出码、标准输出和标准错误。"""

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.tools.base_tool import BaseTool
from myagent.tools.schemas import ToolErrorInfo, ToolResult


logger = logging.getLogger(__name__)


class ShellArgs(BaseModel):
    """Shell 工具的输入参数。"""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(min_length=1, description="需要执行的 Shell 命令，支持管道、重定向及多条命令。")
    cwd: str | None = Field(default=None, min_length=1, description="命令执行目录，支持绝对路径和相对路径，默认使用当前进程工作目录。")
    timeout: int = Field(default=60, ge=1, le=300, description="命令执行超时时间，单位为秒，默认 60，最大 300。")
    max_output_bytes: int = Field(default=20000, ge=1, le=100000, description="标准输出和标准错误各自最多保留的字节数，默认 20000。")


class ShellTool(BaseTool):
    """在指定工作目录中执行 Shell 命令。"""

    name = "execute_shell"
    description = (
        "在指定工作目录执行 Shell 命令，适用于运行程序、测试、构建和项目管理。"
        "支持管道、重定向及组合命令，默认在当前进程工作目录执行。"
        "命令可能修改或删除文件，执行前应确认操作意图。"
        "返回退出码、标准输出和标准错误，支持超时及输出截断。"
    )
    args_schema = ShellArgs

    @staticmethod
    def _failure(code: str, message: str) -> ToolResult:
        """构造命令执行失败结果。"""
        return ToolResult(success=False, content=message, error=ToolErrorInfo(code=code, message=message))

    @staticmethod
    async def _read_stream(stream: asyncio.StreamReader, limit: int) -> tuple[str, bool]:
        """持续读取子进程输出，只保留指定大小，避免大量输出占用内存。"""
        output = bytearray()
        truncated = False

        while chunk := await stream.read(8192):
            remaining = max(0, limit - len(output))
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True

        return output.decode("utf-8", errors="replace"), truncated

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        """终止超时或取消的子进程，POSIX 系统同时终止其进程组。"""
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            elif process.returncode is None:
                process.kill()
        except ProcessLookupError:
            pass

        await process.wait()

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """异步执行 Shell 命令，参数由 ToolExecutor 提前校验。"""
        command = arguments["command"]
        timeout = arguments["timeout"]
        max_output_bytes = arguments["max_output_bytes"]
        cwd = Path(arguments["cwd"]).expanduser().resolve() if arguments["cwd"] else Path.cwd()

        # 1. 检查命令与执行目录
        if not command.strip():
            return self._failure("INVALID_COMMAND", "Shell 命令不能为空")
        if not cwd.exists():
            return self._failure("WORKDIR_NOT_FOUND", f"工作目录不存在：{cwd}")
        if not cwd.is_dir():
            return self._failure("INVALID_WORKDIR", f"指定路径不是目录：{cwd}")

        # 2. 创建异步子进程，分别捕获标准输出和标准错误
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=(os.name == "posix"),
            )
        except OSError:
            logger.exception("Shell 子进程启动失败")
            return self._failure("SHELL_ERROR", "Shell 子进程启动失败")

        stdout_task = asyncio.create_task(self._read_stream(process.stdout, max_output_bytes))
        stderr_task = asyncio.create_task(self._read_stream(process.stderr, max_output_bytes))

        # 3. 等待命令执行，同时限制执行时间
        try:
            async with asyncio.timeout(timeout):
                await process.wait()
                (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(stdout_task, stderr_task)

        except TimeoutError:
            await self._stop_process(process)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            return self._failure("COMMAND_TIMEOUT", f"命令执行超时（{timeout} 秒），已终止进程")

        except asyncio.CancelledError:
            await self._stop_process(process)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            raise  # 保留任务取消信号，不转换为普通工具错误

        # 4. 整理执行结果，非零退出码表示命令执行失败
        exit_code = process.returncode
        success = exit_code == 0
        truncated = stdout_truncated or stderr_truncated

        content = f"退出码：{exit_code}\n标准输出：\n{stdout or '(无)'}\n标准错误：\n{stderr or '(无)'}"
        if truncated:
            content += "\n[输出已截断，请缩小输出范围或调整 max_output_bytes]"

        return ToolResult(
            success=success,
            content=content,
            data={
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "truncated": truncated,
            },
            error=None if success else ToolErrorInfo(
                code="COMMAND_FAILED",
                message=f"Shell 命令执行失败，退出码：{exit_code}",
            ),
        )