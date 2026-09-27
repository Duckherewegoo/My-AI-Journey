from typing import List, Optional
from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage
)
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate


# 总结专用提示词
SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """
你是对话历史压缩总结助手。
任务：把下面多轮用户与AI的对话，浓缩成一段精简、完整、信息不丢失的摘要文本。
要求：
1. 保留用户核心诉求、关键数据、提问目标、工具返回的重要结果；
2. 删除重复闲聊、冗余修饰；
3. 摘要简短精炼，不超过200字；
4. 不要新增不存在的信息，不编造内容。
    """.strip()),
    ("human", "待压缩对话记录：\n{chat_history}")
])


def summarize_chat_history(llm: BaseChatModel, chat_messages: List[BaseMessage]) -> str:
    """
    调用LLM对一段对话消息列表生成摘要文本
    """
    # 把消息拼接成可读文本
    history_blocks = []
    for msg in chat_messages:
        if isinstance(msg, HumanMessage):
            history_blocks.append(f"用户：{msg.content}")
        elif isinstance(msg, AIMessage):
            history_blocks.append(f"AI：{msg.content}")
    full_text = "\n".join(history_blocks)

    chain = SUMMARY_PROMPT | llm
    summary = chain.invoke({"chat_history": full_text})
    return summary.content


def compress_context_messages(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    max_recent_rounds: int = 6,
    token_threshold: int = 1800
) -> List[BaseMessage]:
    """
    核心工具：自动压缩上下文消息
    逻辑：
    1. 分离系统消息（全部置顶永久保留）
    2. 取出所有人机对话历史
    3. 如果对话总长度超过token阈值：
       - 把旧对话压缩成一条AI摘要消息
       - 只保留最新max_recent_rounds轮原始对话
    4. 返回：系统消息 + 摘要(如有) + 最新N轮对话
    """
    # 1. 拆分系统消息、普通对话消息
    system_msgs: List[SystemMessage] = []
    chat_msgs: List[BaseMessage] = []
    for m in messages:
        if isinstance(m, SystemMessage):
            system_msgs.append(m)
        else:
            chat_msgs.append(m)

    if not chat_msgs:
        return system_msgs

    # 粗略估算文本长度替代token计数（简易方案，不用额外库）
    total_text_len = sum(len(m.content) for m in chat_msgs)
    # 粗略换算：1汉字≈2token
    total_token_est = total_text_len * 2

    # 未超阈值，直接原样返回
    if total_token_est < token_threshold:
        return system_msgs + chat_msgs

    # 超过阈值：分割旧历史 + 最新保留轮数
    split_idx = len(chat_msgs) - max_recent_rounds
    if split_idx <= 0:
        return system_msgs + chat_msgs

    old_history = chat_msgs[:split_idx]
    recent_history = chat_msgs[split_idx:]

    # 旧历史生成摘要，封装成一条AI消息
    summary_text = summarize_chat_history(llm, old_history)
    summary_msg = AIMessage(content=f"【历史对话摘要】{summary_text}")

    # 重组最终上下文
    final_messages = system_msgs + [summary_msg] + recent_history
    return final_messages


def auto_trim_and_summarize(
    llm: BaseChatModel,
    messages: List[BaseMessage],
    max_retain: int = 8,
    threshold_tokens: int = 2000
) -> List[BaseMessage]:
    """
    对外简易入口函数，直接丢入state["messages"]即可使用
    """
    return compress_context_messages(
        llm=llm,
        messages=messages,
        max_recent_rounds=max_retain,
        token_threshold=threshold_tokens
    )
