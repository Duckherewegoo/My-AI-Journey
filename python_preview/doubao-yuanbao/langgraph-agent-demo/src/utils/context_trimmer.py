from typing import List
from langchain_core.messages import BaseMessage, SystemMessage


def trim_messages(messages: List[BaseMessage], max_count: int = 12) -> List[BaseMessage]:
    """
    截断对话历史，保留最近消息，控制上下文长度
    保留规则：系统消息 + 最近 max_count 条对话消息
    """
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    chat_msgs = [m for m in messages if not isinstance(m, SystemMessage)]

    if len(chat_msgs) <= max_count:
        return messages

    return system_msgs + chat_msgs[-max_count:]
