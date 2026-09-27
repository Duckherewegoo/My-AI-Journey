"""
基础Agent类
===========
所有智能体的基类，提供通用能力：
- LangChain集成
- Function Calling能力
- 工具动态加载
- 提示词模板渲染
- 记忆管理
"""
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.prompts import MessagesPlaceholder

from ..prompts.templates import PromptTemplateEngine
from ..skills.registry import SkillRegistry


class BaseAgent(ABC):
    """智能体基类 - 全1.x原生API实现"""
    role: str = "base"
    system_prompt_key: str = "base_agent"

    def __init__(
        self,
        llm: BaseChatModel,
        prompt_engine: PromptTemplateEngine,
        skill_registry: SkillRegistry,
    ):
        self.llm = llm
        self.prompt_engine = prompt_engine
        self.skill_registry = skill_registry

        self._tools: List[BaseTool] = []
        self._tool_bound_llm = None  # 绑定工具后的LLM实例，替代原AgentExecutor
        self.refresh_tools()

    def get_system_prompt(self, context: Optional[Dict] = None) -> str:
        """获取渲染后的系统提示词"""
        return self.prompt_engine.render(
            self.system_prompt_key,
            role=self.role,
            **(context or {})
        )

    def refresh_tools(self) -> None:
        """从注册中心刷新工具列表，重建绑定工具的LLM"""
        self._tools = self.skill_registry.get_all_tools()
        self._build_tool_llm()

    def _build_tool_llm(self) -> None:
        """LangChain 1.x标准工具绑定：全模型通用，替代废弃的create_tool_calling_agent"""
        if not self._tools:
            self._tool_bound_llm = None
            return
        # 1.x官方标准工具绑定方式，自动适配模型的tool calling协议
        self._tool_bound_llm = self.llm.bind_tools(self._tools)

    async def invoke_with_tools(
        self,
        query: str,
        system_context: Optional[Dict] = None,
        chat_history: Optional[List[BaseMessage]] = None,
        max_iterations: int = 10,
    ) -> Dict[str, Any]:
        """
        带工具调用的执行入口（1.x原生实现，返回格式与旧版完全兼容）
        """
        # 初始化消息链，统一使用元组格式（1.x标准写法）
        messages = [
            ("system", self.get_system_prompt(system_context)),
            *(chat_history or []),
            ("human", query),
        ]

        intermediate_steps = []
        tool_calls_list = []
        last_ai_msg = None

        # 无工具时直接调用LLM
        if self._tool_bound_llm is None:
            result = await self.llm.ainvoke(messages)
            return {
                "output": result.content,
                "intermediate_steps": [],
                "tool_calls": [],
            }

        # 工具调用循环，完全替代原AgentExecutor的核心逻辑
        for _ in range(max_iterations):
            ai_msg: AIMessage = await self._tool_bound_llm.ainvoke(messages)
            last_ai_msg = ai_msg
            messages.append(ai_msg)

            # 无工具调用，结束循环
            if not ai_msg.tool_calls:
                break

            # 批量执行所有工具调用
            for tool_call in ai_msg.tool_calls:
                # 匹配对应工具
                target_tool = next(
                    (t for t in self._tools if t.name == tool_call["name"]), None)
                if not target_tool:
                    tool_result = f"Error: Tool {tool_call['name']} not found"
                else:
                    try:
                        tool_result = await target_tool.ainvoke(tool_call["args"])
                    except Exception as e:
                        tool_result = f"Tool execution error: {str(e)}"

                # 记录中间步骤（格式与旧版完全兼容）
                intermediate_steps.append((tool_call, tool_result))
                tool_calls_list.append(tool_call["name"])

                # 将工具结果写入消息链
                messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tool_call["id"]
                ))

        return {
            "output": last_ai_msg.content if last_ai_msg else "",
            "intermediate_steps": intermediate_steps,
            "tool_calls": tool_calls_list,
        }

    async def simple_chat(self, query: str, system_context: Optional[Dict] = None) -> str:
        """纯对话调用（无工具）"""
        messages = [
            ("system", self.get_system_prompt(system_context)),
            ("human", query),
        ]
        result = await self.llm.ainvoke(messages)
        return result.content

    @abstractmethod
    async def run(self, *args, **kwargs):
        pass
