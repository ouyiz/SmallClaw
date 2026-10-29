"""
LLM 抽象基类，定义统一的模型调用接口。
"""

from abc import ABC, abstractmethod
from typing import Any

from myagent.core.message import Message


class BaseLLM(ABC):
    """所有 LLM 实现的抽象基类。"""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Message:
        """调用大语言模型并返回统一格式的响应。

        Args:
            messages: 模型输入消息列表，包含系统提示词、对话历史等。
            tools: 可选的工具定义列表，包含工具名称、描述和参数 Schema。

        Returns:
            Message: 统一格式的模型响应，可能包含文本或工具调用请求。

        Raises:
            LLMError: 模型调用失败时抛出，由具体实现类负责处理。
        """
        ...