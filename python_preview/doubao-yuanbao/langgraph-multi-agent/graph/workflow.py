"""
工作流定义
使用LangGraph构建多智能体协作写作工作流
"""

from typing import Dict, Any, Optional, TypedDict, Annotated
from langchain_core.language_models import BaseChatModel
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from agents.base_agent import AgentState
from agents.researcher import ResearchAgent
from agents.writer import WriterAgent
from agents.reviewer import ReviewerAgent
from agents.editor import EditorAgent


class WorkflowConfig(BaseModel):
    """工作流配置"""
    llm: BaseChatModel = Field(description="语言模型实例")
    max_iterations: int = Field(default=3, description="最大迭代次数")
    researcher_config: Optional[Dict[str, Any]] = Field(
        default=None, description="研究智能体配置"
    )
    writer_config: Optional[Dict[str, Any]] = Field(
        default=None, description="写作智能体配置"
    )
    reviewer_config: Optional[Dict[str, Any]] = Field(
        default=None, description="审核智能体配置"
    )
    editor_config: Optional[Dict[str, Any]] = Field(
        default=None, description="编辑智能体配置"
    )


class WorkflowState(TypedDict):
    """工作流状态类型"""
    topic: str
    research_notes: list
    draft_content: str
    review_feedback: str
    final_content: str
    current_step: str
    iteration_count: int
    max_iterations: int
    metadata: dict


def _state_to_agent_state(state: WorkflowState) -> AgentState:
    """
    将工作流状态转换为智能体状态

    Args:
        state: 工作流状态

    Returns:
        智能体状态
    """
    return AgentState(
        topic=state.get("topic", ""),
        research_notes=state.get("research_notes", []),
        draft_content=state.get("draft_content", ""),
        review_feedback=state.get("review_feedback", ""),
        final_content=state.get("final_content", ""),
        current_step=state.get("current_step", "research"),
        iteration_count=state.get("iteration_count", 0),
        max_iterations=state.get("max_iterations", 3),
        metadata=state.get("metadata", {}),
    )


def _agent_state_to_state(agent_state: AgentState, state: WorkflowState) -> WorkflowState:
    """
    将智能体状态更新到工作流状态

    Args:
        agent_state: 智能体状态
        state: 原始工作流状态

    Returns:
        更新后的工作流状态
    """
    return {
        **state,
        "topic": agent_state.topic,
        "research_notes": agent_state.research_notes,
        "draft_content": agent_state.draft_content,
        "review_feedback": agent_state.review_feedback,
        "final_content": agent_state.final_content,
        "current_step": agent_state.current_step,
        "iteration_count": agent_state.iteration_count,
        "max_iterations": agent_state.max_iterations,
        "metadata": agent_state.metadata,
    }


def create_workflow(config: WorkflowConfig):
    """
    创建多智能体协作写作工作流

    Args:
        config: 工作流配置

    Returns:
        编译后的LangGraph工作流
    """
    # 初始化各个智能体
    researcher = ResearchAgent(
        llm=config.llm,
        **(config.researcher_config or {}),
    )

    writer = WriterAgent(
        llm=config.llm,
        **(config.writer_config or {}),
    )

    reviewer = ReviewerAgent(
        llm=config.llm,
        **(config.reviewer_config or {}),
    )

    editor = EditorAgent(
        llm=config.llm,
        **(config.editor_config or {}),
    )

    # 定义节点函数
    async def research_node(state: WorkflowState) -> WorkflowState:
        """研究节点"""
        agent_state = _state_to_agent_state(state)
        result = await researcher.run(agent_state)
        return _agent_state_to_state(result, state)

    async def write_node(state: WorkflowState) -> WorkflowState:
        """写作节点"""
        agent_state = _state_to_agent_state(state)
        result = await writer.run(agent_state)
        return _agent_state_to_state(result, state)

    async def review_node(state: WorkflowState) -> WorkflowState:
        """审核节点"""
        agent_state = _state_to_agent_state(state)
        result = await reviewer.run(agent_state)
        return _agent_state_to_state(result, state)

    async def edit_node(state: WorkflowState) -> WorkflowState:
        """编辑节点"""
        agent_state = _state_to_agent_state(state)
        result = await editor.run(agent_state)
        return _agent_state_to_state(result, state)

    # 定义条件边函数
    def should_continue_writing(state: WorkflowState) -> str:
        """
        判断是否继续写作（审核后是否需要修改）

        Args:
            state: 当前状态

        Returns:
            下一个节点名称
        """
        needs_revision = state.get("metadata", {}).get("needs_revision", False)
        iteration_count = state.get("iteration_count", 0)
        max_iterations = state.get("max_iterations", 3)

        if needs_revision and iteration_count < max_iterations:
            return "write"
        else:
            return "edit"

    # 创建状态图
    workflow = StateGraph(WorkflowState)

    # 添加节点
    workflow.add_node("research", research_node)
    workflow.add_node("write", write_node)
    workflow.add_node("review", review_node)
    workflow.add_node("edit", edit_node)

    # 设置入口点
    workflow.set_entry_point("research")

    # 添加边
    workflow.add_edge("research", "write")
    workflow.add_edge("write", "review")

    # 添加条件边（审核后决定是继续修改还是进入编辑）
    workflow.add_conditional_edges(
        "review",
        should_continue_writing,
        {
            "write": "write",
            "edit": "edit",
        },
    )

    workflow.add_edge("edit", END)

    # 编译工作流
    compiled_workflow = workflow.compile()

    return compiled_workflow


def create_initial_state(
    topic: str,
    max_iterations: int = 3,
) -> WorkflowState:
    """
    创建初始状态

    Args:
        topic: 写作主题
        max_iterations: 最大迭代次数

    Returns:
        初始工作流状态
    """
    return {
        "topic": topic,
        "research_notes": [],
        "draft_content": "",
        "review_feedback": "",
        "final_content": "",
        "current_step": "research",
        "iteration_count": 0,
        "max_iterations": max_iterations,
        "metadata": {},
    }
