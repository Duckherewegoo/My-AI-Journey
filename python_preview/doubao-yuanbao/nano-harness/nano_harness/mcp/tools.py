"""
MCP 工具适配器
==============
将本地Skill和工具适配为MCP格式的桥接层。
核心作用：
1. 将LangChain工具转换为MCP工具
2. 将MCP工具转换为LangChain工具
3. 统一工具注册与发现机制
4. 支持动态加载和热插拔
这是Skill机制与MCP协议的关键集成点。
"""
import logging
from typing import List, Dict, Any, Callable, Optional
from langchain_core.tools import BaseTool, StructuredTool
from .server import MCPServer
from .client import MCPClient

logger = logging.getLogger(__name__)


class MCPToolAdapter:
    """
    MCP工具适配器

    负责在MCP协议和本地工具系统之间做双向转换。

    高级特性：
    - 双向转换：LangChain ↔ MCP
    - 批量导入导出
    - Schema自动生成
    - 工具分组与命名空间
    """

    def __init__(self, namespace: str = "nano"):
        self.namespace = namespace
        # 保留原有属性，不破坏兼容性

    # ===== LangChain → MCP =====

    def langchain_to_mcp(self, tool: BaseTool) -> Dict[str, Any]:
        """
        将LangChain工具转换为MCP工具定义

        Args:
            tool: LangChain工具对象

        Returns:
            MCP格式的工具定义
        """
        # 从LangChain工具提取信息
        name = f"{self.namespace}_{tool.name}"
        description = tool.description

        # 尝试从工具的args_schema提取JSON Schema
        input_schema = self._extract_schema(tool)

        # 修复：包装invoke方法，兼容MCP的关键字参数调用方式
        def handler(**kwargs):
            return tool.invoke(kwargs)

        return {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }

    def _extract_schema(self, tool: BaseTool) -> Dict[str, Any]:
        """从LangChain工具提取输入参数的JSON Schema"""
        try:
            if hasattr(tool, 'args_schema') and tool.args_schema:
                # 使用Pydantic模型生成JSON Schema
                schema = tool.args_schema.model_json_schema()
                # 移除不必要的字段
                schema.pop("title", None)
                return schema
        except Exception as e:
            logger.warning(f"Extract schema failed for tool {tool.name}: {e}")

        # 默认Schema
        return {
            "type": "object",
            "properties": {
                "input": {
                    "type": "string",
                    "description": "工具输入参数"
                }
            },
        }

    def register_skill_to_mcp(self, skill: Any, server: MCPServer):
        """
        将一个Skill的所有工具注册到MCP服务端

        这是Skill机制与MCP协议集成的核心方法。
        """
        tools = skill.get_tools()

        for tool in tools:
            if not isinstance(tool, BaseTool):
                logger.warning(f"Skip invalid tool: {type(tool)}")
                continue

            mcp_tool = self.langchain_to_mcp(tool)
            server.register_tool(
                name=mcp_tool["name"],
                description=mcp_tool["description"],
                handler=mcp_tool["handler"],
                input_schema=mcp_tool["input_schema"],
            )

    # ===== MCP → LangChain =====

    def mcp_to_langchain_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
    ) -> BaseTool:
        """
        将MCP工具转换为LangChain工具

        Args:
            name: 工具名称
            description: 工具描述
            handler: 处理函数

        Returns:
            LangChain工具对象
        """
        return StructuredTool.from_function(
            func=handler,
            name=name,
            description=description,
        )

    def import_mcp_tools(
        self,
        client: MCPClient,
        skill_registry: Any = None,
    ) -> List[BaseTool]:
        """
        从远程MCP服务导入所有工具

        Args:
            client: MCP客户端
            skill_registry: Skill注册中心（可选，用于注册）

        Returns:
            LangChain工具列表
        """
        # 获取远程工具
        remote_tools = client.list_tools()

        langchain_tools = []
        for tool_info in remote_tools:
            # 修复：通过默认参数捕获循环变量，解决闭包迟绑定bug
            def make_tool_call(tool_name=tool_info.name):
                def tool_call(**kwargs):
                    return client.call_tool(tool_name, kwargs)
                return tool_call

            tool_func = make_tool_call()

            # 创建LangChain工具
            tool = StructuredTool.from_function(
                func=tool_func,
                name=f"mcp_{client.service_name}_{tool_info.name}",
                description=f"[来自MCP服务 {client.service_name}] {tool_info.description}",
            )
            langchain_tools.append(tool)

        # 如果有Skill注册中心，注册进去
        if skill_registry:
            # 动态创建虚拟Skill包装远程工具
            class RemoteMCPSkill:
                name = f"mcp_{client.service_name}"
                description = f"来自MCP服务 {client.service_name} 的远程工具集"

                def get_tools(self):
                    return langchain_tools

            skill_registry.register(RemoteMCPSkill())

        return langchain_tools

    # ===== 服务端创建 =====

    def create_server_from_skills(
        self,
        skills: List,
        name: str = "nano-harness-mcp",
    ) -> MCPServer:
        """
        从一组Skill创建MCP服务端

        这是快速暴露本地能力为MCP服务的便捷方法。
        """
        server = MCPServer(name=name)

        for skill in skills:
            self.register_skill_to_mcp(skill, server)

        return server
