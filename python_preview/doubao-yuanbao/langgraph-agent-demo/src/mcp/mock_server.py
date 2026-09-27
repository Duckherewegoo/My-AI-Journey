from typing import Dict, Any, Callable
import jieba
from numpy import true_divide
from utils.context_summarizer import auto_trim_and_summarize
from openai import OpenAI
import os


class MockMCPServer:
    """模拟MCP协议服务端，提供外部工具能力"""

    def __init__(self, llm: OpenAI):
        self.llm = llm
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """注册默认MCP工具"""
        self._tools["mcp_summarize"] = {
            "description": "对长文本进行摘要提炼",
            "parameters": {"text": "待摘要的长文本内容"},
            "handler": self._summarize_handler
        }
        self._tools["mcp_keyword_extract"] = {
            "description": "提取文本中的核心关键词",
            "parameters": {"text": "待提取关键词的文本"},
            "handler": self._keyword_handler
        }

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """列出所有可用工具（MCP标准接口）"""
        return self._tools

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """调用工具（MCP标准接口）"""
        if tool_name not in self._tools:
            return f"MCP错误：工具 {tool_name} 不存在"
        return self._tools[tool_name]["handler"](**args)

    def _summarize_handler(self, text: str) -> str:
        """文本摘要工具：调用注入的LLM对输入文本做摘要提炼"""
        # 1. 包装为标准对话消息格式，变量名拆分避免歧义
        messages = [{"role": "user", "content": text}]

        # 2. 调用摘要函数，使用实例注入的llm
        summary = auto_trim_and_summarize(
            llm=self.llm,
            messages=messages,
            max_retain=8,
            threshold_tokens=1000
        )

        # 3. 格式化返回
        return f"摘要：{summary[:50]}...（核心内容已提炼，共{len(summary)}字）"

    @staticmethod
    def _keyword_handler(text: str) -> str:
        """模拟关键词提取工具"""
        # 简单模拟，实际可接入NLP模型
        words = jieba.cut(text, cut_all=True)
        keywords = words[:5] if len(words) >= 5 else words
        return f"提取关键词：{', '.join(keywords)}"
