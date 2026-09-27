"""
基础智能体类
所有智能体的基类，提供通用的功能和接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """智能体状态模型"""
    topic: str = Field(description="写作主题")
    research_notes: List[str] = Field(default_factory=list, description="研究笔记")
    draft_content: str = Field(default="", description="草稿内容")
    review_feedback: str = Field(default="", description="审核反馈")
    final_content: str = Field(default="", description="最终内容")
    current_step: str = Field(default="research", description="当前步骤")
    iteration_count: int = Field(default=0, description="迭代次数")
    max_iterations: int = Field(default=3, description="最大迭代次数")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class BaseAgent(ABC):
    """
    智能体基类
    提供所有智能体共有的功能和接口
    """

    def __init__(
        self,
        llm: BaseChatModel,
        name: str,
        description: str,
        system_prompt: Optional[str] = None,
    ):
        """
        初始化基础智能体

        Args:
            llm: 语言模型实例
            name: 智能体名称
            description: 智能体描述
            system_prompt: 系统提示词
        """
        self.llm = llm
        self.name = name
        self.description = description
        self.system_prompt = system_prompt or self._get_default_system_prompt()

    def _get_default_system_prompt(self) -> str:
        """获取默认的系统提示词"""
        return f"你是{self.name}，{self.description}。请专业、认真地完成你的工作。"

    def _build_messages(
        self,
        human_message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[BaseMessage]:
        """
        构建消息列表

        Args:
            human_message: 用户消息
            context: 上下文信息

        Returns:
            消息列表
        """
        messages = [
            SystemMessage(content=self.system_prompt),
        ]

        if context:
            context_str = "\n".join([f"{k}: {v}" for k, v in context.items()])
            messages.append(SystemMessage(content=f"上下文信息：\n{context_str}"))

        messages.append(HumanMessage(content=human_message))
        return messages

    async def _call_llm(
        self,
        messages: List[BaseMessage],
        **kwargs,
    ) -> str:
        """
        调用语言模型

        Args:
            messages: 消息列表
            **kwargs: 其他参数

        Returns:
            模型回复内容
        """
        response = await self.llm.ainvoke(messages, **kwargs)
        return response.content

    @abstractmethod
    async def run(self, state: AgentState) -> AgentState:
        """
        运行智能体

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name}>"
