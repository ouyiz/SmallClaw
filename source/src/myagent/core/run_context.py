"""Agent 单次运行上下文：记录运行标识、工作目录及执行计数。"""

from pathlib import Path
from uuid import uuid4

from myagent.core.errors import RunContextError


class RunContext:
    """管理单次 Agent Run 的运行状态。"""

    def __init__(self, session_id: str, cwd: str | Path) -> None:
        """初始化运行状态，自动生成唯一的 run_id。"""
        if not isinstance(session_id, str) or not session_id.strip():
            raise RunContextError("session_id 必须是非空字符串")

        self.session_id: str = session_id
        self.run_id: str = uuid4().hex
        self.step_count: int = 0
        self.tool_call_count: int = 0
        self.cwd: Path

        self.set_cwd(cwd)

    def next_step(self) -> None:
        """记录一次 AgentLoop 执行步骤。"""
        self.step_count += 1

    def record_tool_call(self) -> None:
        """记录一次工具调用。"""
        self.tool_call_count += 1

    def set_cwd(self, path: str | Path) -> None:
        """更新工作目录，要求目标路径存在且为目录。"""
        if not isinstance(path, (str, Path)) or (isinstance(path, str) and not path.strip()):
            raise RunContextError("工作目录必须是非空字符串或 Path 对象")

        try:
            cwd = Path(path).expanduser().resolve(strict=True)
            if not cwd.is_dir():
                raise RunContextError(f"工作目录不是有效目录：{cwd}")
        except OSError as exc:
            raise RunContextError(f"工作目录不存在或无法访问：{path}") from exc

        self.cwd = cwd