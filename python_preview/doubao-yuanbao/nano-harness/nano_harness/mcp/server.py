"""
MCP 服务端
==========
将本地的Skill和工具暴露为标准MCP服务。
支持的MCP能力：
- Tools：工具调用（核心）
- Resources：资源访问（文件、数据等）
- Prompts：提示词模板
- Logging：日志推送
传输协议：
- stdio：标准输入输出（本地进程）
- HTTP + SSE：网络传输（远程访问）
"""
import json
import asyncio
import sys
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from pydantic import create_model, Field

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema


@dataclass
class MCPResource:
    """MCP资源定义"""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"


@dataclass
class MCPPrompt:
    """MCP提示词定义"""
    name: str
    description: str
    arguments: List[Dict] = None  # 修复：默认值后续统一初始化


class MCPServer:
    """
    MCP 服务端实现

    核心功能：
    1. 工具注册与发现
    2. 工具调用执行
    3. 资源管理
    4. 提示词模板
    5. 多传输协议支持

    高级特性：
    - 能力协商（capabilities negotiation）
    - 渐进式增强
    - 错误处理与标准化
    """

    def __init__(self, name: str = "nano-harness", version: str = "0.1.0"):
        self.name = name
        self.version = version

        # 注册的工具、资源、提示词
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._prompts: Dict[str, MCPPrompt] = {}

        # 修复：初始化提供者字典，避免AttributeError
        self._resource_providers: Dict[str, Callable] = {}
        self._prompt_providers: Dict[str, Callable] = {}

        # 修复：修正能力声明，未实现的功能不声明
        self._capabilities = {
            "tools": {"listChanged": False},
            "resources": {"listChanged": False},
            "prompts": {"listChanged": False},
            "logging": {},
        }

        # 请求ID计数器
        self._request_id = 0

    # ===== 工具注册 =====

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        input_schema: Optional[Dict] = None,
    ):
        """
        注册一个工具

        Args:
            name: 工具名称
            description: 工具描述
            handler: 处理函数
            input_schema: 输入参数的JSON Schema
        """
        self._tools[name] = handler

        # 默认Schema
        if input_schema is None:
            input_schema = {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "输入参数"}
                },
            }

        self._tool_schemas[name] = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
        )

    def register_resource(
        self,
        uri: str,
        name: str,
        description: str,
        content_provider: Callable,
        mime_type: str = "text/plain",
    ):
        """注册一个资源"""
        self._resources[uri] = MCPResource(
            uri=uri,
            name=name,
            description=description,
            mime_type=mime_type,
        )
        self._resource_providers[uri] = content_provider

    def register_prompt(
        self,
        name: str,
        description: str,
        template_provider: Callable,
        arguments: Optional[List[Dict]] = None,
    ):
        """注册一个提示词模板"""
        self._prompts[name] = MCPPrompt(
            name=name,
            description=description,
            arguments=arguments or [],
        )
        self._prompt_providers[name] = template_provider

    # ===== MCP 协议处理 =====

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理MCP请求（同步入口，用于stdio模式）

        这是MCP协议的核心分发器，根据method路由到对应处理函数
        """
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            result = self._dispatch(method, params)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except ValueError as e:
            # 修复：规范JSON-RPC错误码
            if "not found" in str(e) or "unknown" in str(e):
                code = -32601  # 方法不存在
            else:
                code = -32602  # 参数无效
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": code,
                    "message": str(e),
                },
            }
        except Exception as e:
            logger.error(f"Handle request error: {e}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,  # 内部错误
                    "message": str(e),
                },
            }

    async def handle_http_request(self, request_body: Dict) -> Dict:
        """处理HTTP请求（异步入口，用于FastAPI集成）"""
        # 同步逻辑放到线程池，避免阻塞事件循环
        return await asyncio.to_thread(self.handle_request, request_body)

    def _dispatch(self, method: str, params: Dict) -> Any:
        """请求分发"""
        # ===== 初始化 =====
        if method == "initialize":
            return self._handle_initialize(params)

        elif method == "notifications/initialized":
            return {}

        # ===== 工具 =====
        elif method == "tools/list":
            return self._handle_tools_list()

        elif method == "tools/call":
            return self._handle_tool_call(params)

        # ===== 资源 =====
        elif method == "resources/list":
            return self._handle_resources_list()

        elif method == "resources/read":
            return self._handle_resources_read(params)

        # ===== 提示词 =====
        elif method == "prompts/list":
            return self._handle_prompts_list()

        elif method == "prompts/get":
            return self._handle_prompts_get(params)

        # ===== Ping =====
        elif method == "ping":
            return {}

        else:
            raise ValueError(f"Unknown method: {method}")

    def _handle_initialize(self, params: Dict) -> Dict:
        """处理初始化请求 - 能力协商"""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": self._capabilities,
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }

    def _handle_tools_list(self) -> Dict:
        """列出所有可用工具"""
        tools = []
        for tool in self._tool_schemas.values():
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            })
        return {"tools": tools}

    def _handle_tool_call(self, params: Dict) -> Dict:
        """调用工具"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        handler = self._tools[name]

        # 执行工具
        try:
            # 修复：用asyncio.run替代手动新建事件循环，更规范安全
            if asyncio.iscoroutinefunction(handler):
                result = asyncio.run(handler(**arguments))
            else:
                result = handler(**arguments)

            # 格式化结果
            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            elif isinstance(result, dict):
                content = [{"type": "text", "text": json.dumps(
                    result, ensure_ascii=False)}]
            else:
                content = [{"type": "text", "text": str(result)}]

            return {
                "content": content,
                "isError": False,
            }

        except Exception as e:
            logger.error(f"Tool call error [{name}]: {e}", exc_info=True)
            return {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }

    def _handle_resources_list(self) -> Dict:
        """列出所有资源"""
        resources = []
        for res in self._resources.values():
            resources.append({
                "uri": res.uri,
                "name": res.name,
                "description": res.description,
                "mimeType": res.mime_type,
            })
        return {"resources": resources}

    def _handle_resources_read(self, params: Dict) -> Dict:
        """读取资源内容"""
        uri = params.get("uri", "")

        if uri not in self._resource_providers:
            raise ValueError(f"Resource not found: {uri}")

        content = self._resource_providers[uri]()

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": self._resources[uri].mime_type,
                    "text": content if isinstance(content, str) else json.dumps(content),
                }
            ]
        }

    def _handle_prompts_list(self) -> Dict:
        """列出所有提示词模板"""
        prompts = []
        for prompt in self._prompts.values():
            prompts.append({
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
            })
        return {"prompts": prompts}

    def _handle_prompts_get(self, params: Dict) -> Dict:
        """获取提示词模板"""
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        if name not in self._prompt_providers:
            raise ValueError(f"Prompt not found: {name}")

        prompt_text = self._prompt_providers[name](**arguments)

        return {
            "description": self._prompts[name].description,
            "messages": [
                {
                    "role": "user",
                    "content": {"type": "text", "text": prompt_text},
                }
            ],
        }

    # ===== 传输层 =====

    def run_stdio(self):
        """
        以stdio模式运行服务端
        从stdin读取JSON-RPC请求，写到stdout
        """
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = self.handle_request(request)
                    print(json.dumps(response, ensure_ascii=False), flush=True)
                except json.JSONDecodeError:
                    # 忽略格式错误的行
                    continue
        except (EOFError, KeyboardInterrupt):
            # 修复：优雅处理EOF和中断信号
            logger.info("MCP server stdio connection closed")
            return

    def get_tools_for_langchain(self) -> List:
        """
        将MCP工具转换为LangChain工具格式
        这是MCP与LangChain集成的桥梁
        """
        from langchain_core.tools import StructuredTool

        tools = []
        for name, tool in self._tool_schemas.items():
            handler = self._tools[name]

            # 修复：动态创建Pydantic参数模型，启用参数校验
            props = tool.input_schema.get("properties", {})
            fields = {}
            for prop_name, prop_info in props.items():
                # 简单映射类型，默认string
                prop_type = str
                if prop_info.get("type") == "integer":
                    prop_type = int
                elif prop_info.get("type") == "number":
                    prop_type = float
                elif prop_info.get("type") == "boolean":
                    prop_type = bool

                fields[prop_name] = (
                    prop_type,
                    Field(default=prop_info.get("default", ""),
                          description=prop_info.get("description", "")),
                )

            # 创建参数模型
            InputModel = create_model(f"{name}_input", **fields)

            # 创建工具，传入参数schema
            tools.append(
                StructuredTool.from_function(
                    func=handler,
                    name=name,
                    description=tool.description,
                    args_schema=InputModel,
                )
            )

        return tools
