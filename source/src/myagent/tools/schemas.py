"""
工具统一返回结构，定义执行结果与错误信息。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolErrorInfo(BaseModel):
    """
    工具执行失败时的结构化错误信息。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")  # 稳定的错误代码，如 FILE_NOT_FOUND
    message: str = Field(min_length=1)                               # 可读的错误描述
    retryable: bool = False                                         # 是否适合重试


class ToolResult(BaseModel):
    """
    工具统一执行结果，供 AgentLoop 和 ToolExecutor 使用。
    """

    model_config = ConfigDict(extra="forbid")

    success: bool                                # 工具是否执行成功
    content: str                                 # 返回给 LLM 的结果文本
    data: dict[str, Any] | None = None           # 可选的结构化业务数据
    error: ToolErrorInfo | None = None           # 失败时的错误信息

    @model_validator(mode="after")
    def validate_result(self) -> "ToolResult":
        """
        保证执行状态与错误信息一致。
        """
        if self.success and self.error is not None:
            raise ValueError("工具执行成功时，error 必须为 None")
        if not self.success and self.error is None:
            raise ValueError("工具执行失败时，必须提供 error")
        return self