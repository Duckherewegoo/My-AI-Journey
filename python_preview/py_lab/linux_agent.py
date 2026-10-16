"""
Linux Expert Agent - 专注于解决 Linux 系统问题的智能助手

这个 Agent 的核心功能：
1. 解答 Linux 系统相关问题
2. 提供故障排查和性能优化建议
3. 引导用户理解底层原理和机制
4. 支持多轮对话，保持上下文连贯
"""

import os
import json
from typing import Annotated
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.graph import MessagesState
from langgraph.graph.message import add_messages
from langchain_core.messages import AnyMessage
from coze_coding_utils.runtime_ctx.context import default_headers
from storage.memory import get_memory_saver

# LLM 配置文件路径
LLM_CONFIG = "config/agent_llm_config.json"

# 默认保留最近 20 轮对话 (40 条消息)
MAX_MESSAGES = 40


def _windowed_messages(old, new):
    """
    滑动窗口机制：只保留最近 MAX_MESSAGES 条消息
    防止对话历史过长导致上下文超限
    """
    return add_messages(old, new)[-MAX_MESSAGES:]  # type: ignore


class AgentState(MessagesState):
    """
    Agent 状态定义
    使用滑动窗口管理消息历史
    """

    messages: Annotated[list[AnyMessage], _windowed_messages]


def build_agent(ctx=None):
    """
    构建 Linux 专家 Agent

    参数:
        ctx: 运行时上下文，用于请求追踪和链路追踪

    返回:
        Agent 实例
    """
    # 获取工作空间路径
    workspace_path = os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects")
    config_path = os.path.join(workspace_path, LLM_CONFIG)

    # 读取 LLM 配置
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 从环境变量获取认证信息
    api_key = os.getenv("COZE_WORKLOAD_IDENTITY_API_KEY")
    base_url = os.getenv("COZE_INTEGRATION_MODEL_BASE_URL")

    # 初始化 LLM 实例
    llm = ChatOpenAI(
        model=cfg["config"].get("model"),
        api_key=api_key,
        base_url=base_url,
        temperature=cfg["config"].get("temperature", 0.7),
        streaming=True,
        timeout=cfg["config"].get("timeout", 600),
        extra_body={"thinking": {"type": cfg["config"].get("thinking", "disabled")}},
        default_headers=default_headers(ctx) if ctx else {},
    )

    # 创建并返回 Agent 实例
    return create_agent(
        model=llm,
        system_prompt=cfg.get("sp"),
        tools=[],  # Linux 专家 Agent 暂时不需要外部工具
        checkpointer=get_memory_saver(),  # 启用短期记忆
        state_schema=AgentState,  # 使用滑动窗口状态
    )
