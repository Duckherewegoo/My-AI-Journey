from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from .state import AgentState
from .nodes import (
    input_moderation_node,
    agent_node,
    tool_execution_node,
    loop_check_node,
    final_analysis_node
)
from mcp.client import MockMCPClient


def build_agent_graph(llm, mcp_client: MockMCPClient, max_steps: int = 6):
    """构建完整智能体图"""
    graph = StateGraph(AgentState)

    # 注册所有节点
    graph.add_node("input_moderation", input_moderation_node)
    graph.add_node("agent", lambda s: agent_node(s, llm, mcp_client))
    graph.add_node("tool_execution", lambda s: tool_execution_node(s, mcp_client))
    graph.add_node("final_analysis", final_analysis_node)

    # 构建边与条件分支
    graph.add_edge(START, "input_moderation")
    graph.add_edge("input_moderation", "agent")
    graph.add_conditional_edges(
        "agent",
        loop_check_node,
        {
            "human_confirm": "tool_execution",
            "final_analysis": "final_analysis"
        }
    )
    graph.add_edge("tool_execution", "agent")
    graph.add_edge("final_analysis", END)

    # 编译：开启人机交互中断（工具执行前人工确认）
    memory = MemorySaver()
    compiled_graph = graph.compile(
        checkpointer=memory,
        interrupt_before=["tool_execution"]  # 工具执行前中断，等待人工确认
    )

    return compiled_graph
