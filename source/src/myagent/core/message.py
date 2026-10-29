from typing import Any, Literal
from pydantic import BaseModel, Field



# 消息角色：系统提示词、用户输入、模型回复、工具结果
MessageRole = Literal["system", "user", "assistant", "tool"]

class Message(BaseModel):
    """
    Agent 内部统一消息格式。
    """

    role: MessageRole                                     # 消息角色
    content: str | None = None                            # 消息文本内容
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)  # 模型请求的工具调用（id、name、arguments）
    tool_call_id: str | None = None                       # 工具结果对应的调用 ID
    metadata: dict[str, Any] = Field(default_factory=dict)  # 附加信息，如时间戳、模型结束原因
    ##Message 继承了 Pydantic 的 BaseModel，已经提供了构造函数，类型校验等