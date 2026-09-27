import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from core.graph import build_agent_graph
from mcp.client import MockMCPClient


def main():
    # 加载环境变量
    load_dotenv()

    # 初始化LLM（默认硅基流动免费接口）
    llm = ChatOpenAI(
        api_key=os.getenv("LLM_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"),
        model=os.getenv("LLM_MODEL"),
        temperature=0.1
    )

    # 初始化MCP客户端并连接
    mcp_client = MockMCPClient()
    mcp_client.connect()

    # 构建智能体图
    max_steps = int(os.getenv("MAX_LOOP_STEPS", 6))
    agent_graph = build_agent_graph(llm, mcp_client, max_steps=max_steps)

    # 会话ID，用于多会话隔离
    config = {"configurable": {"thread_id": "demo-session-001"}}

    # ========== 示例1：普通工具调用 + ReAct循环 ==========
    print("=== 示例1：计算器工具调用 ===")
    initial_state = {
        "messages": [HumanMessage(content="计算 1234 * 567 + 890 的结果是多少")],
        "loop_count": 0,
        "max_steps": max_steps,
        "human_feedback": None,
        "analysis_result": None,
        "csv_file_path": None
    }

    # 首次执行，到工具调用前会中断（人机确认）
    result = agent_graph.invoke(initial_state, config=config)
    print("当前状态：等待人工确认工具执行")

    # 人工确认，继续执行（resume恢复执行）
    result = agent_graph.invoke(None, config=config)
    print(f"最终结果：{result['analysis_result']}\n")

    # ========== 示例2：多轮对话 + 上下文记忆 ==========
    print("=== 示例2：多轮对话上下文验证 ===")
    state2 = {
        "messages": result["messages"] + [HumanMessage(content="刚才的结果再除以2等于多少")],
        "loop_count": 0,
        "max_steps": max_steps,
        "human_feedback": None,
        "analysis_result": None,
        "csv_file_path": None
    }
    result2 = agent_graph.invoke(state2, config={"configurable": {"thread_id": "demo-session-002"}})
    # 跳过确认直接执行
    result2 = agent_graph.invoke(None, config={"configurable": {"thread_id": "demo-session-002"}})
    print(f"最终结果：{result2['analysis_result']}")


if __name__ == "__main__":
    main()
