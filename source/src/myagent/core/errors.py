"""
myAgent 框架统一异常定义。
"""


class AgentError(Exception):
    """Agent 框架基础异常，所有自定义框架异常均继承此类。"""


class ConfigError(AgentError):
    """配置文件加载、解析或校验失败。"""


class LLMError(AgentError):
    """LLM API 调用或模型响应处理失败。"""


class ToolError(AgentError):
    """工具加载、注册或初始化失败。"""


class AgentLoopError(AgentError):
    """Agent 执行流程发生不可恢复的错误。"""

class RunContextError(AgentError):
    """运行上下文初始化或更新失败。"""