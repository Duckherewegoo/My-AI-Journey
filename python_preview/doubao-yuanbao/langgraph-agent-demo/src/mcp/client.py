from typing import List
from langchain_core.tools import tool
from .mock_server import MockMCPServer


class MockMCPClient:
    """MCP协议客户端，对接MCP服务端"""
    def __init__(self):
        self.server = MockMCPServer()
        self._connected = False

    def connect(self) -> None:
        """连接MCP服务端"""
        self._connected = True

    def list_tools(self):
        """获取服务端所有工具"""
        if not self._connected:
            raise RuntimeError("MCP客户端未连接")
        return self.server.list_tools()

    def call_tool(self, tool_name: str, args: dict) -> str:
        """调用MCP服务端工具"""
        if not self._connected:
            raise RuntimeError("MCP客户端未连接")
        return self.server.call_tool(tool_name, args)

    def get_langchain_tools(self) -> List:
        """将MCP工具转换为LangChain可识别的Tool格式"""
        if not self._connected:
            self.connect()

        tools = []
        for name, info in self.list_tools().items():
            # 动态创建工具函数
            def make_tool(tool_name, tool_desc):
                @tool
                def mcp_tool(**kwargs):
                    return self.call_tool(tool_name, kwargs)
                mcp_tool.name = tool_name
                mcp_tool.description = tool_desc["description"]
                return mcp_tool

            tools.append(make_tool(name, info))

        return tools
