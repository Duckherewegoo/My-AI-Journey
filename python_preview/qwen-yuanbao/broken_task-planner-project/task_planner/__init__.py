"""
task_planner — 通用任务规划助手
"""
__version__ = "1.0.0"

from .config import (
    DASHSCOPE_API_KEY,
    LLM_INTENT_MODEL,
    LLM_PLANNER_MODEL,
    LLM_NODE_MODEL,
    TASK_STATUS,
    STATUS_TEXT,
    STATUS_COLOR,
    STATUS_BORDER,
)

__all__ = [
    "__version__",
    "DASHSCOPE_API_KEY",
    "LLM_INTENT_MODEL",
    "LLM_PLANNER_MODEL",
    "LLM_NODE_MODEL",
    "TASK_STATUS",
    "STATUS_TEXT",
    "STATUS_COLOR",
    "STATUS_BORDER",
]
