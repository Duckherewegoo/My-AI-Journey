"""
NanoHarness - 轻量级多智能体编排框架
=====================================
集 Function Calling、MCP协议、多智能体、Skill机制、提示词工程、
多模态处理、人机交互、LangChain、REST API 于一体的微型AI操作系统。

核心设计哲学：小而全，可插拔，易扩展。
"""

__version__ = "0.1.0"
__author__ = "NanoHarness Team"

from .harness import Harness
from .agent.base import BaseAgent
from .skills.registry import SkillRegistry

__all__ = ["Harness", "BaseAgent", "SkillRegistry"]
