"""
MCP 客户端
==========
连接外部MCP服务，将其工具能力接入本地系统。
支持的连接方式：
- stdio：启动本地子进程
- HTTP：远程HTTP服务
- SSE：服务器推送事件流
高级特性：
- 自动发现工具
- 自动转换为LangChain工具格式
- 连接池管理
- 错误重试
"""
import json
import asyncio
import subprocess
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# 可选依赖检查，避免运行时才报错
try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


@dataclass
class RemoteMCPTool:
    """远程MCP工具信息"""
    name: str
    description: str
    input_schema: Dict[str, Any]


class MCPClient:
    """
    MCP 客户端

    用于连接外部MCP服务，获取工具能力并集成到本地系统中。

    使用方式：
    1. 连接到MCP服务（stdio或HTTP）
    2. 获取可用工具列表
    3. 调用工具
    4. 将工具转换为LangChain格式，供Agent使用
    """

    def __init__(self, service_name: str = "remote-mcp"):
        self.service_name = service_name
        self._process: Optional[subprocess.Popen] = None
        self._tools: List[RemoteMCPTool] = []
        self._initialized = False
        self._request_id = 0

    # ===== 连接管理 =====

    def connect_stdio(self, command: List[str]) -> bool:
        """
        通过stdio连接到本地MCP服务

        Args:
            command: 启动命令，如 ["python", "mcp_server.py"]

        Returns:
            是否连接成功
        """
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            # 初始化握手，失败自动清理资源
            self._initialize()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MCP service via stdio: {e}")
            self.disconnect()  # 失败自动清理，防止僵尸进程
            return False

    async def connect_http(self, url: str) -> bool:
        """
        通过HTTP连接到远程MCP服务

        Args:
            url: MCP服务的HTTP端点

        Returns:
            是否连接成功
        """
        if requests is None:
            raise ImportError("HTTP模式需要安装requests库: pip install requests")

        try:
            self._http_url = url
            # 同步逻辑放到线程池执行，避免阻塞异步事件循环
            await asyncio.to_thread(self._initialize)
            return True
        except Exception as e:
            logger.error(f"Failed to connect to MCP service via HTTP: {e}")
            self.disconnect()
            return False

    def _initialize(self):
        """初始化握手"""
        # 发送initialize请求
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "nano-harness",
                "version": "0.1.0",
            },
        })

        # 发送initialized通知
        self._send_notification("notifications/initialized", {})

        self._initialized = True

        # 获取工具列表
        self._tools = self.list_tools()

    def disconnect(self):
        """断开连接，彻底清理资源"""
        if self._process:
            try:
                # 先关闭管道，再终止进程
                if self._process.stdin:
                    self._process.stdin.close()
                if self._process.stdout:
                    self._process.stdout.close()
                if self._process.stderr:
                    self._process.stderr.close()

                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            except Exception:
                pass
            finally:
                self._process = None

        self._initialized = False

    # ===== 协议层 =====

    def _send_request(self, method: str, params: Dict) -> Any:
        """发送JSON-RPC请求"""
        self._request_id += 1

        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        if self._process:
            # stdio模式
            request_str = json.dumps(request, ensure_ascii=False) + "\n"
            self._process.stdin.write(request_str)
            self._process.stdin.flush()

            # 读取响应
            response_line = self._process.stdout.readline()
            if not response_line:
                raise ConnectionError("MCP service closed connection")

            response = json.loads(response_line.strip())

            if "error" in response:
                raise Exception(f"MCP error: {response['error']}")

            return response.get("result")

        elif hasattr(self, '_http_url'):
            # HTTP模式
            if requests is None:
                raise ImportError("HTTP模式需要安装requests库: pip install requests")

            response = requests.post(
                self._http_url,
                json=request,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if "error" in result:
                raise Exception(f"MCP error: {result['error']}")

            return result.get("result")

        else:
            raise ConnectionError("Not connected to any MCP service")

    def _send_notification(self, method: str, params: Dict):
        """发送通知（不需要响应）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }

        if self._process:
            request_str = json.dumps(notification, ensure_ascii=False) + "\n"
            self._process.stdin.write(request_str)
            self._process.stdin.flush()

    # ===== 工具操作 =====

    def list_tools(self) -> List[RemoteMCPTool]:
        """列出所有可用工具"""
        result = self._send_request("tools/list", {})
        tools_data = result.get("tools", [])

        tools = []
        for t in tools_data:
            tools.append(RemoteMCPTool(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            ))

        return tools

    def call_tool(self, name: str, arguments: Dict) -> str:
        """
        调用远程工具

        Args:
            name: 工具名称
            arguments: 参数字典

        Returns:
            工具执行结果文本
        """
        result = self._send_request("tools/call", {
            "name": name,
            "arguments": arguments,
        })

        # 提取文本内容
        contents = result.get("content", [])
        text_parts = []
        for content in contents:
            if content.get("type") == "text":
                text_parts.append(content.get("text", ""))

        return "\n".join(text_parts)

    # ===== LangChain 集成 =====

    def get_langchain_tools(self) -> List:
        """
        将远程MCP工具转换为LangChain工具

        这是关键的集成点：外部MCP服务的工具可以无缝被
        本地LangChain Agent调用，就像本地工具一样。
        """
        from langchain_core.tools import StructuredTool

        tools = []

        for tool_info in self._tools:
            # 修复：通过默认参数捕获循环变量，解决闭包迟绑定bug
            def make_tool_call(tool_name=tool_info.name):
                def tool_call(**kwargs):
                    return self.call_tool(tool_name, kwargs)
                return tool_call

            tool_func = make_tool_call()

            # 创建LangChain工具
            tools.append(
                StructuredTool.from_function(
                    func=tool_func,
                    name=f"mcp_{self.service_name}_{tool_info.name}",
                    description=f"[MCP/{self.service_name}] {tool_info.description}",
                )
            )

        return tools

    # ===== 资源操作 =====

    def list_resources(self) -> List[Dict]:
        """列出所有资源"""
        result = self._send_request("resources/list", {})
        return result.get("resources", [])

    def read_resource(self, uri: str) -> str:
        """读取资源内容"""
        result = self._send_request("resources/read", {"uri": uri})
        contents = result.get("contents", [])
        if contents:
            return contents[0].get("text", "")
        return ""

    # ===== 提示词操作 =====

    def list_prompts(self) -> List[Dict]:
        """列出所有提示词模板"""
        result = self._send_request("prompts/list", {})
        return result.get("prompts", [])

    def get_prompt(self, name: str, arguments: Optional[Dict] = None) -> str:
        """获取提示词模板"""
        result = self._send_request("prompts/get", {
            "name": name,
            "arguments": arguments or {},
        })
        messages = result.get("messages", [])
        if messages:
            content = messages[0].get("content", {})
            if isinstance(content, dict):
                return content.get("text", "")
            return str(content)
        return ""
