"""
MCP 协议包
===========
Model Context Protocol 实现

MCP是Anthropic推出的开放协议，用于在AI模型和外部工具/数据源之间
建立标准化连接。本实现包含：
- MCP服务端：将本地Skill/工具暴露为MCP服务
- MCP客户端：连接外部MCP服务，获取工具能力
- 工具自动发现与注册

支持的传输方式：
- stdio：本地进程间通信
- HTTP/REST：远程网络通信
- SSE：服务器推送事件
"""

from .server import MCPServer
from .client import MCPClient
from .tools import MCPToolAdapter

__all__ = ["MCPServer", "MCPClient", "MCPToolAdapter"]
