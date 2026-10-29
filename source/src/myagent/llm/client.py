"""
统一 LLM 客户端：适配 OpenAI 兼容协议与 Anthropic Messages API。
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlsplit

from anthropic import APIError as AnthropicAPIError, AsyncAnthropic
from openai import APIError as OpenAIAPIError, AsyncOpenAI

from myagent.core.errors import ConfigError, LLMError
from myagent.core.message import Message
from myagent.llm.base_llm import BaseLLM
from myagent.llm.usage import UsageTracker


class LLMClient(BaseLLM):
    """
    通过统一 Message 接口调用不同协议的模型。
    """

    def __init__(self, config: dict[str, Any], usage_tracker: UsageTracker | None = None):
        self.config = dict(config)

        if not self.config.get("model_name"):
            raise ConfigError("模型配置缺少 model_name")
        if self.config.get("protocol") not in ("openai", "anthropic"):
            raise ConfigError("protocol 仅支持 'openai' 或 'anthropic'")

        self.client: AsyncOpenAI | AsyncAnthropic = self._create_client()
        self.usage_tracker = usage_tracker if usage_tracker is not None else UsageTracker()

    def _create_client(self) -> AsyncOpenAI | AsyncAnthropic:
        """
        根据配置创建 SDK 客户端，密钥仅从环境变量读取。
        """
        key_env = self.config.get("api_key_env")
        api_key = os.getenv(key_env) if key_env else None
        base_url = self.config.get("base_url")
        protocol = self.config["protocol"]

        if not api_key:
            is_local = base_url and urlsplit(base_url).hostname in {"localhost", "127.0.0.1", "::1"}
            if protocol in ("openai", "anthropic")  and is_local:
                api_key = "local"  
            else:
                raise ConfigError(f"未设置 API Key 环境变量：{key_env or '(未配置 api_key_env)'}")

        options: dict[str, Any] = {
            "api_key": api_key,
            "timeout": self.config.get("timeout", 60),
            "max_retries": self.config.get("max_retries", 2),
        }
        if base_url:
            options["base_url"] = base_url

        return AsyncOpenAI(**options) if protocol == "openai" else AsyncAnthropic(**options)

    def _build_request(self, messages: list[Message], tools: list[dict[str, Any]] | None) -> dict[str, Any]:
        """
        将 myAgent 内部统一的 Message 和工具定义转换为目标 API 协议的请求参数。
        支持 OpenAI Chat Completions 和 Anthropic Messages 两种协议。
        """
        protocol = self.config["protocol"]
        request: dict[str, Any] = {"model": self.config["model_name"]}

        # 设置模型生成参数，未配置 temperature 时不传递
        if self.config.get("temperature") is not None:
            request["temperature"] = self.config["temperature"]

        # ==================== OpenAI 协议 ====================
        if protocol == "openai":
            # 优先使用 max_completion_tokens，否则使用 max_tokens
            if self.config.get("max_completion_tokens") is not None:
                request["max_completion_tokens"] = self.config["max_completion_tokens"]
            elif self.config.get("max_tokens") is not None:
                request["max_tokens"] = self.config["max_tokens"]

            items = []
            for msg in messages:
                # 普通消息直接使用 role 和 content
                item: dict[str, Any] = {"role": msg.role, "content": msg.content}

                # Assistant 请求工具调用时，转换为 OpenAI 的 tool_calls 格式
                if msg.role == "assistant" and msg.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call["id"],              # 工具调用 ID，用于关联执行结果
                            "type": "function",
                            "function": {
                                "name": call["name"],      # 工具名称
                                # OpenAI 要求 arguments 为 JSON 字符串，而非 Python 字典
                                "arguments": call["arguments"] if isinstance(call["arguments"], str)
                                            else json.dumps(call["arguments"], ensure_ascii=False),
                            },
                        }
                        for call in msg.tool_calls
                    ]

                # 工具执行结果使用 role="tool"，通过 tool_call_id 关联之前的调用
                if msg.role == "tool":
                    if not msg.tool_call_id:
                        raise ValueError("工具结果消息缺少 tool_call_id")
                    item["tool_call_id"] = msg.tool_call_id
                    item["content"] = msg.content or ""

                items.append(item)

            request["messages"] = items

        # ==================== Anthropic 协议 ====================
        else:
            # Anthropic 要求 max_tokens，未配置时默认 4096
            request["max_tokens"] = self.config.get("max_tokens") or 4096
            systems: list[str] = []
            items: list[dict[str, Any]] = []

            for msg in messages:
                # Anthropic 的 System Prompt 是独立参数，不放在 messages 列表中
                if msg.role == "system":
                    if msg.content:
                        systems.append(msg.content)

                # Anthropic 没有独立的 tool 角色，工具结果以 user 消息中的 tool_result 表示
                elif msg.role == "tool":
                    if not msg.tool_call_id:
                        raise ValueError("工具结果消息缺少 tool_call_id")

                    result: dict[str, Any] = {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,  # 对应之前 tool_use 的 ID
                        "content": msg.content or "",
                    }
                    if msg.metadata.get("is_error"):
                        result["is_error"] = True        # 标记工具执行失败

                    # 多个连续工具结果合并到同一条 user 消息，避免重复创建消息
                    if items and items[-1]["role"] == "user" and isinstance(items[-1]["content"], list):
                        items[-1]["content"].append(result)
                    else:
                        items.append({"role": "user", "content": [result]})

                # Anthropic 的 assistant 消息由 text、tool_use 等内容块组成
                elif msg.role == "assistant":
                    blocks: list[dict[str, Any]] = []
                    if msg.content:
                        blocks.append({"type": "text", "text": msg.content})

                    for call in msg.tool_calls:
                        arguments = call["arguments"]

                        # Anthropic 的 tool_use.input 要求 JSON 对象，而不是 JSON 字符串
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except json.JSONDecodeError as exc:
                                raise LLMError("Anthropic 工具参数必须是合法 JSON 对象") from exc
                        if not isinstance(arguments, dict):
                            raise LLMError("Anthropic 工具参数必须是 JSON 对象")

                        blocks.append({
                            "type": "tool_use",
                            "id": call["id"],             # 工具调用 ID
                            "name": call["name"],         # 工具名称
                            "input": arguments,          # 工具参数对象
                        })

                    items.append({"role": "assistant", "content": blocks})

                # 其余消息作为普通 user 消息
                else:
                    items.append({"role": "user", "content": msg.content or ""})

            # 将多个 System Prompt 合并为 Anthropic 的独立 system 参数
            if systems:
                request["system"] = "\n\n".join(systems)
            request["messages"] = items

        # ==================== 工具定义转换 ====================
        # tools 由 ToolRegistry 提供，统一格式在这里转换为具体协议格式
        if tools:
            definitions = []
            for tool in tools:
                # 兼容扁平工具定义和 OpenAI function 嵌套定义
                func = tool.get("function", tool)
                name = func.get("name")
                schema = func.get("parameters", func.get("input_schema"))

                # 工具必须包含名称及参数 JSON Schema
                if not name or not isinstance(schema, dict):
                    raise ValueError("工具定义必须包含 name 和参数 JSON Schema")

                desc = func.get("description", "")
                if protocol == "openai":
                    # OpenAI：使用 function.parameters 描述工具输入参数
                    definitions.append({
                        "type": "function",
                        "function": {"name": name, "description": desc, "parameters": schema},
                    })
                else:
                    # Anthropic：使用 input_schema 描述工具输入参数
                    definitions.append({"name": name, "description": desc, "input_schema": schema})

            request["tools"] = definitions

        # 返回可通过 **request 解包并传给 SDK 的请求参数
        return request

    async def chat(self, messages: list[Message], tools: list[dict[str, Any]] | None = None) -> Message:
        """
        调用模型，统一解析返回消息并记录 Token 用量。
        """
        if not messages:
            raise ValueError("messages 不能为空")

        request = self._build_request(messages, tools)

        try:
            if self.config["protocol"] == "openai":
                response = await self.client.chat.completions.create(**request)
            else:
                response = await self.client.messages.create(**request)
        except (OpenAIAPIError, AnthropicAPIError) as exc:
            raise LLMError(f"模型 API 调用失败：{type(exc).__name__}") from exc

        message = self._parse_response(response)

        # 统计由 UsageTracker 负责，LLMClient 不计算费用
        usage = message.metadata["usage"]
        self.usage_tracker.record(
            model=self.config["model_name"],
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cached_tokens=usage["cached_tokens"],
        )
        return message

    def _parse_response(self, response: Any) -> Message:
        """
        将不同协议的模型响应转换为统一 Message，提取文本、工具调用及 Token 用量。
        """

        # ==================== OpenAI 协议 ====================
        if self.config["protocol"] == "openai":
            if not response.choices:
                raise LLMError("模型返回空 choices")

            # 获取模型的第一条回复
            choice = response.choices[0]
            content = choice.message.content
            calls = []

            # 将 OpenAI 的 function tool_calls 转换为内部统一格式
            for call in choice.message.tool_calls or []:
                if call.type != "function":
                    raise LLMError(f"不支持的工具调用类型：{call.type}")

                raw = call.function.arguments
                try:
                    arguments = json.loads(raw)  # 将 JSON 字符串解析为 Python 对象
                except json.JSONDecodeError:
                    arguments = raw  # 保留错误参数，由 ToolExecutor 统一处理

                calls.append({
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": arguments,
                })

            # 提取 Token 用量，兼容标准 OpenAI 和部分兼容接口的缓存统计字段
            usage = response.usage
            details = getattr(usage, "prompt_tokens_details", None)
            cached = getattr(details, "cached_tokens", None)
            if cached is None:
                cached = getattr(usage, "prompt_cache_hit_tokens", 0)

            counts = {
                "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
                "cached_tokens": cached or 0,
            }
            finish_reason = choice.finish_reason

        # ==================== Anthropic 协议 ====================
        else:
            texts, calls = [], []

            # Anthropic 的 content 由多个内容块组成，分别提取文本和工具调用
            for block in response.content:
                if block.type == "text":
                    texts.append(block.text)
                elif block.type == "tool_use":
                    calls.append({
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.input,  # Anthropic 的工具参数本身就是对象
                    })

            content = "\n".join(texts) or None
            usage = response.usage

            # Anthropic 将普通输入、缓存创建和缓存读取 Token 分别统计
            counts = {
                "input_tokens": (getattr(usage, "input_tokens", 0) or 0)
                                + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
                                + (getattr(usage, "cache_read_input_tokens", 0) or 0),
                "output_tokens": getattr(usage, "output_tokens", 0) or 0,
                "cached_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            }
            finish_reason = response.stop_reason

        # ==================== 统一响应格式 ====================
        # 不同协议最终都转换为 Message，AgentLoop 无需关心底层 API 的差异
        return Message(
            role="assistant",
            content=content,
            tool_calls=calls,
            metadata={
                "finish_reason": finish_reason,  # 模型停止生成的原因
                "model": response.model,          # 实际响应的模型名称
                "usage": counts,                  # 本次请求的 Token 用量
            },
        )