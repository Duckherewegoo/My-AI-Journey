"""
API 模块
=========
提供REST API接口，支持通过HTTP调用Harness系统。

功能：
- 对话接口：/chat
- 任务接口：/task (创建/查询/列表)
- Skill管理：/skills
- MCP接口：/mcp
- WebSocket实时流式输出
"""

from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
