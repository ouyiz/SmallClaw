"""上下文数据结构：定义提供给 LLM 的完整 Context。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from myagent.core.message import Message


class Context(BaseModel):
    """由 ContextEngine 构建的完整模型上下文。"""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str = Field(
        description="完整系统提示词，由 PromptBuilder 组装。"
    )
    conversation: list[Message] = Field(
        default_factory=list,
        description="对话历史，包括用户消息、Assistant 回复、工具调用与结果，以及压缩后的历史摘要。"
    )
    additional_context: list[Message] = Field(
        default_factory=list,
        description="附加上下文，包括相关记忆、任务信息、检索资料及插件提供的内容。"
    )
    tools: list[dict[str, Any]] = Field(
        default_factory=list,
        description="本次模型调用可用的工具定义，由 ToolRegistry 完成协议适配。"
    )