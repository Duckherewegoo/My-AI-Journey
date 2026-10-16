import asyncio
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
import operator

# 1. 定义全局状态（每个用户会话独立一份）
class PlanState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]  # 对话历史，自带记忆
    task_goal: str          # 解析后的结构化任务目标
    plan_steps: list[dict]  # 规划步骤列表
    tool_suggestions: dict  # 步骤对应的工具建议
    review_feedback: str    # 评审反馈

# 2. 定义工具（示例）
def search_info(query: str) -> str:
    """搜索信息，辅助规划"""
    return f"关于{query}的参考信息：..."

tools = [search_info]
tool_node = ToolNode(tools)

# 3. 定义各角色节点（异步）
async def parse_requirement(state: PlanState):
    """需求解析官角色"""
    last_msg = state["messages"][-1].content
    # 实际替换为LLM调用，解析任务目标
    return {"task_goal": f"解析后的任务：{last_msg}"}

async def generate_plan(state: PlanState):
    """方案规划师角色"""
    # 实际替换为LLM调用，生成结构化步骤
    steps = [
        {"step": 1, "content": "先完成需求调研"},
        {"step": 2, "content": "制定执行方案"},
        {"step": 3, "content": "落地执行与校验"}
    ]
    return {"plan_steps": steps}

async def match_tools(state: PlanState):
    """工具顾问角色（并行分支）"""
    return {"tool_suggestions": {"1": "使用搜索工具", "2": "使用文档工具"}}

async def merge_plan(state: PlanState):
    """方案整合节点（并行汇聚）"""
    merged = []
    for step in state["plan_steps"]:
        step_id = str(step["step"])
        step["tool"] = state["tool_suggestions"].get(step_id, "无")
        merged.append(step)
    return {"plan_steps": merged}

async def review_plan(state: PlanState):
    """方案评审员角色"""
    return {"review_feedback": "规划合格"}

def should_continue(state: PlanState):
    """条件边：判断是否需要重写规划"""
    if "合格" in state["review_feedback"]:
        return END
    return "generate_plan"

# 4. 构建图
def build_graph():
    graph = StateGraph(PlanState)
    
    # 添加节点
    graph.add_node("parse", parse_requirement)
    graph.add_node("generate_plan", generate_plan)
    graph.add_node("match_tools", match_tools)
    graph.add_node("merge", merge_plan)
    graph.add_node("review", review_plan)
    graph.add_node("tools", tool_node)
    
    # 定义流转边
    graph.add_edge(START, "parse")
    # 解析后分出两个并行分支
    graph.add_edge("parse", "generate_plan")
    graph.add_edge("parse", "match_tools")
    # 并行节点完成后汇聚到整合节点
    graph.add_edge("generate_plan", "merge")
    graph.add_edge("match_tools", "merge")
    # 整合→评审→条件分支
    graph.add_edge("merge", "review")
    graph.add_conditional_edges("review", should_continue)
    
    # 启用Checkpoint（多用户隔离+记忆的核心）
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)

# 5. 多用户调用示例
async def main():
    app = build_graph()
    
    # 用户A的独立会话
    user_a_config = {"configurable": {"thread_id": "user_001_session_001"}}
    result_a = await app.ainvoke(
        {"messages": [HumanMessage(content="帮我规划一个LangGraph项目")]},
        config=user_a_config
    )
    print("用户A的规划：", result_a["plan_steps"])
    
    # 用户B的独立会话，完全隔离
    user_b_config = {"configurable": {"thread_id": "user_002_session_001"}}
    result_b = await app.ainvoke(
        {"messages": [HumanMessage(content="帮我规划一次旅行")]},
        config=user_b_config
    )
    print("用户B的规划：", result_b["plan_steps"])
    
    # 用户A第二轮提问，自动加载上下文记忆
    result_a2 = await app.ainvoke(
        {"messages": [HumanMessage(content="把第二步改得更详细一点")]},
        config=user_a_config
    )
    print("用户A第二轮结果：", result_a2["plan_steps"])

if __name__ == "__main__":
    asyncio.run(main())
