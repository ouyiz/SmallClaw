from abc import ABC, abstractmethod
from .config import AgentConfig
from .loop import AgentLoop
from ..llm.base import BaseLLM

# 成员变量：config,llm,loop,name,
# 成员函数：__init__(),run(),name(),__str__()

class BaseAgent(ABC):
    """
    Agent 抽象基类，定义通用属性和运行接口。
    """

    def __init__(self, config: AgentConfig, llm: BaseLLM, loop: AgentLoop):
        self.config = config   # Agent 配置
        self.llm = llm         # 模型调用实例
        self.loop = loop       # 执行循环

    @property
    def name(self) -> str:
        """
        获取 Agent 名称。
        """
        return self.config.name

    @abstractmethod
    async def run(self, input_text: str, session_id: str | None = None) -> str:
        """统一运行入口，由具体 Agent 实现。"""
        pass

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name})"