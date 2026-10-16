from typing import TypedDict, Annotated, List, Any, Optional
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """智能体全局状态定义"""
    # 对话消息历史，自动追加归约（核心）
    messages: Annotated[List[BaseMessage], add_messages]
    # 循环计数，防止死循环
    loop_count: int
    # 最大允许循环步数
    max_steps: int
    # 人工反馈内容（人机交互用）
    human_feedback: Optional[str]
    # 分析结果缓存
    analysis_result: Optional[Any]
    # 用户上传的CSV文件路径
    csv_file_path: Optional[str]
