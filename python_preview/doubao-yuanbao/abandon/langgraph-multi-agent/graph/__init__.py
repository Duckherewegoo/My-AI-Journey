"""
多智能体协作写作系统 - 工作流模块
使用LangGraph定义多智能体协作流程
"""

from .workflow import create_workflow, WorkflowConfig

__all__ = [
    "create_workflow",
    "WorkflowConfig",
]
