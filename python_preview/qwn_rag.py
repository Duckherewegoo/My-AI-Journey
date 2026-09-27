#!/usr/bin/env python3
"""
LangChain 1.2.x RAG 系统 (修复版)
解决 ChatPromptValue 类型不兼容问题
"""

import os
import sys
import time
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import hashlib
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ============================================
# 第一部分：导入与配置
# ============================================

print("🔧 导入依赖库并检查环境...")

# 1. 首先检查关键的 dashscope SDK
try:
    import dashscope
    from dashscope import TextEmbedding, Generation

    print(f"✅ dashscope SDK 导入成功")
except ImportError as e:
    print(f"❌ dashscope SDK 导入失败: {e}")
    print("请运行: pip install dashscope")
    sys.exit(1)

# 2. 检查 LangChain 相关库
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.document_loaders import TextLoader
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough, RunnableLambda
    from langchain_chroma import Chroma

    print("✅ LangChain 核心库导入成功")
except ImportError as e:
    print(f"❌ LangChain 库导入失败: {e}")
    sys.exit(1)

# 3. 检查 langchain_classic 用于高级检索
try:
    from langchain_classic.retrievers import (
        ContextualCompressionRetriever,
        EnsembleRetriever,
        BM25Retriever,
    )
    from langchain_classic.retrievers.document_compressors import LLMChainExtractor

    print("✅ langchain_classic 检索器导入成功")
except ImportError as e:
    print(f"⚠️ langchain_classic 导入警告: {e}")
    print("高级检索功能将受限，但基础RAG仍可运行。")

# 4. 检查其他依赖
try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("⚠️ numpy 未安装，部分功能可能受限")

# 5. 验证 API Key
API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not API_KEY:
    print("❌ 错误: 未找到环境变量 DASHSCOPE_API_KEY")
    print("请按照以下步骤设置：")
    print("1. 访问: https://dashscope.aliyuncs.com/")
    print("2. 创建API Key (格式: sk-xxxx)")
    print("3. 运行: export DASHSCOPE_API_KEY=your-key-here")
    print("或创建 .env 文件并添加: DASHSCOPE_API_KEY=your-key-here")
    sys.exit(1)

print(f"✅ API Key 检查通过 (前8位: {API_KEY[:8]}...)")
print("=" * 60)

# ============================================
# 第二部分：阿里云百炼 API 客户端 (修复版)
# ============================================


class QwenEmbeddings:
    """
    阿里云百炼 Embedding 服务封装
    使用官方 TextEmbedding API
    """

    def __init__(self, api_key: str = None, model: str = "text-embedding-v2"):
        self.api_key = api_key or API_KEY
        self.model = model
        # 设置 API Key
        dashscope.api_key = self.api_key
        print(f"✅ QwenEmbeddings 初始化 (模型: {self.model})")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """为多个文档生成嵌入向量"""
        if not texts:
            return []

        embeddings = []
        print(f"📡 正在调用千问Embedding API处理 {len(texts)} 个文本...")

        for i, text in enumerate(texts):
            try:
                # 调用阿里云百炼 Embedding API
                resp = TextEmbedding.call(model=self.model, input=text)

                if resp.status_code == 200:
                    # 提取嵌入向量
                    embedding = resp.output["embeddings"][0]["embedding"]
                    embeddings.append(embedding)
                    if (i + 1) % 10 == 0:
                        print(f"  ✅ 已处理 {i+1}/{len(texts)} 个文本")
                else:
                    print(
                        f"❌ Embedding API 调用失败 (文本 {i}): {resp.code} - {resp.message}"
                    )
                    # 返回零向量作为回退
                    zero_vec = [0.0] * 1536
                    embeddings.append(zero_vec)

            except Exception as e:
                print(f"❌ Embedding 处理异常 (文本 {i}): {e}")
                zero_vec = [0.0] * 1536
                embeddings.append(zero_vec)

        print(f"✅ 所有文本嵌入完成")
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """为单个查询生成嵌入向量"""
        try:
            resp = TextEmbedding.call(model=self.model, input=text)

            if resp.status_code == 200:
                return resp.output["embeddings"][0]["embedding"]
            else:
                print(f"❌ 查询Embedding失败: {resp.code} - {resp.message}")
                return [0.0] * 1536
        except Exception as e:
            print(f"❌ 查询Embedding异常: {e}")
            return [0.0] * 1536


class QwenChatLLM:
    """
    阿里云百炼 Chat 服务封装 (修复版)
    解决 ChatPromptValue 类型不兼容问题
    """

    def __init__(self, api_key: str = None, model: str = "qwen-plus"):
        self.api_key = api_key or API_KEY
        self.model = model
        dashscope.api_key = self.api_key
        print(f"✅ QwenChatLLM 初始化 (模型: {self.model})")

    def invoke(self, input_data: Union[str, dict, Any]) -> str:
        """同步调用 - 支持多种输入类型"""
        return self._call_api(self._extract_text(input_data))

    async def ainvoke(self, input_data: Union[str, dict, Any]) -> str:
        """异步调用 - 支持多种输入类型"""
        return self._call_api(self._extract_text(input_data))

    def _extract_text(self, input_data: Union[str, dict, Any]) -> str:
        """从各种输入类型中提取文本"""
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, dict):
            # 如果是字典，尝试提取content
            if "content" in input_data:
                return input_data["content"]
            elif "prompt" in input_data:
                return input_data["prompt"]
            elif "question" in input_data:
                return input_data["question"]
            elif "query" in input_data:
                return input_data["query"]
            else:
                # 尝试转换为字符串
                return str(input_data)
        else:
            # 对于 LangChain 的 PromptValue 对象
            try:
                # 尝试获取字符串表示
                if hasattr(input_data, "to_string"):
                    return input_data.to_string()
                elif hasattr(input_data, "to_messages"):
                    messages = input_data.to_messages()
                    # 提取最后一个用户消息
                    for msg in reversed(messages):
                        if hasattr(msg, "content"):
                            return str(msg.content)
                elif hasattr(input_data, "text"):
                    return input_data.text
            except:
                pass

            # 最后尝试直接转换为字符串
            return str(input_data)

    def _call_api(self, input_text: str) -> str:
        """实际调用阿里云百炼 API"""
        try:
            # 确保输入是字符串且不为空
            if not input_text or not isinstance(input_text, str):
                return "错误: 输入文本无效或为空"

            # 清理文本
            input_text = input_text.strip()
            if not input_text:
                return "错误: 输入文本为空"

            # 限制文本长度
            if len(input_text) > 8000:
                input_text = input_text[:8000] + "..."

            response = Generation.call(
                model=self.model,
                messages=[{"role": "user", "content": input_text}],
                result_format="message",
            )

            if response.status_code == 200:
                return response.output.choices[0].message.content
            else:
                error_msg = f"API调用失败: {response.code} - {response.message}"
                print(f"❌ {error_msg}")
                return f"抱歉，调用大模型时发生错误: {error_msg}"

        except Exception as e:
            error_msg = f"API调用异常: {str(e)}"
            print(f"❌ {error_msg}")
            return f"抱歉，处理请求时发生异常: {error_msg}"

    def __call__(self, input_data: Union[str, dict, Any]) -> str:
        """使对象可调用"""
        return self.invoke(input_data)


# ============================================
# 第三部分：文档处理器
# ============================================


class DocumentProcessor:
    """文档加载与处理器"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            add_start_index=True,
        )

    def create_sample_documents(self) -> List[Document]:
        """创建包含阿里云百炼和RAG相关知识的示例文档"""
        sample_data = [
            {
                "content": """阿里云百炼（DashScope）是大模型服务平台，提供多种AI模型API。
                核心服务包括：文本生成（如qwen-plus）、文本嵌入（text-embedding-v2）、图像生成、语音合成等。
                调用方式：通过dashscope SDK或OpenAI兼容接口，需配置API Key (格式: sk-xxxx)。""",
                "metadata": {"source": "dashscope_intro.txt", "topic": "阿里云百炼"},
            },
            {
                "content": """获取API Key步骤：
                1. 访问阿里云百炼控制台
                2. 选择地域（如华北2-北京）
                3. 进入API Key页面，点击"创建API KEY"
                4. 选择归属业务空间（建议默认空间）
                5. 复制生成的Key (sk-开头)
                注意：API Key需妥善保管，避免泄露。""",
                "metadata": {"source": "api_key_guide.txt", "topic": "API配置"},
            },
            {
                "content": """RAG（检索增强生成）系统架构：
                1. 文档加载：从多种格式读取文档
                2. 文本分割：将长文档切分为语义块
                3. 向量化：使用Embedding模型转换为向量
                4. 存储：向量存入数据库（如Chroma）
                5. 检索：根据查询查找相似文档
                6. 生成：结合检索结果生成回答。""",
                "metadata": {"source": "rag_architecture.txt", "topic": "RAG原理"},
            },
            {
                "content": """LangChain 1.2.x 的重要变化：
                - 模块化：text_splitter移到langchain_text_splitters包
                - 检索器：原检索器功能移至langchain_classic.retrievers
                - 异步优先：推荐使用异步接口提高性能
                - 类型增强：更好的类型提示和错误检查。""",
                "metadata": {"source": "langchain_changes.txt", "topic": "LangChain"},
            },
            {
                "content": """高级RAG技术包括：
                1. 查询扩展：生成多个相关查询提高召回率
                2. 混合检索：结合向量检索和BM25关键词检索
                3. 重排序：对初步结果进行优化排序
                4. 上下文压缩：提取最相关的文本片段
                这些技术可显著提升回答准确性和相关性。""",
                "metadata": {"source": "advanced_rag.txt", "topic": "高级RAG"},
            },
        ]

        documents = []
        for item in sample_data:
            doc = Document(page_content=item["content"], metadata=item["metadata"])
            documents.append(doc)

        print(f"✅ 创建了 {len(documents)} 个示例文档")
        return documents

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """分割文档为chunks"""
        if not documents:
            return []

        chunks = self.text_splitter.split_documents(documents)

        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "chunk_id": f"chunk_{i}",
                    "total_chunks": len(chunks),
                    "hash": hashlib.md5(chunk.page_content.encode()).hexdigest()[:8],
                }
            )

        print(f"📊 文档分割: {len(documents)} → {len(chunks)} chunks")
        return chunks


# ============================================
# 第四部分：Native RAG 系统 (修复版)
# ============================================


class NativeRAGSystem:
    """基础RAG系统 - 使用真实的千问API"""

    def __init__(
        self,
        api_key: str = None,
        embedding_model: str = "text-embedding-v2",
        chat_model: str = "qwen-plus",
        persist_dir: str = "./chroma_db_native",
    ):

        print(f"\n🔧 初始化 Native RAG 系统...")

        # 初始化阿里云百炼客户端
        self.embeddings = QwenEmbeddings(api_key, embedding_model)
        self.llm = QwenChatLLM(api_key, chat_model)

        self.persist_dir = persist_dir
        self.vectorstore = None
        self.retriever = None
        self.rag_chain = None

        print(f"✅ 使用模型: Embedding({embedding_model}), Chat({chat_model})")

    def build_knowledge_base(self, documents: List[Document]):
        """构建知识库"""
        print("\n🔨 构建 Native RAG 知识库...")
        print("  注: 正在调用真实的千问Embedding API，非模拟版本")

        # 1. 创建向量存储（将自动调用真实的embed_documents）
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_dir,
        )

        # 2. 创建检索器
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity", search_kwargs={"k": 4}
        )

        # 3. 构建RAG链
        self._build_rag_chain()

        print(f"✅ Native RAG 知识库构建完成")
        print(f"   存储路径: {self.persist_dir}")
        print(f"   文档数量: {len(documents)}")

        return self

    def _build_rag_chain(self):
        """构建RAG处理链"""
        template = """你是一个专业的AI助手，请基于以下上下文信息回答问题。

上下文信息：
{context}

用户问题：
{question}

要求：
1. 基于上下文信息提供准确回答
2. 如果上下文没有相关信息，请说明"根据提供的信息，无法回答此问题"
3. 回答要结构清晰、完整
4. 使用中文回答

请开始回答："""

        prompt = ChatPromptTemplate.from_template(template)

        def format_docs(docs: List[Document]) -> str:
            """格式化检索到的文档"""
            formatted = []
            for i, doc in enumerate(docs, 1):
                source = doc.metadata.get("source", "未知来源")
                content = doc.page_content
                formatted.append(f"[文档{i}] 来源: {source}\n内容: {content}")
            return "\n\n".join(formatted)

        # 构建 LangChain Runnable
        self.rag_chain = (
            {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

    async def query(self, question: str) -> Dict[str, Any]:
        """查询RAG系统"""
        if not self.rag_chain:
            raise ValueError("请先调用 build_knowledge_base() 构建知识库")

        print(f"\n🔍 Native RAG 查询: {question}")
        start_time = time.time()

        try:
            # 执行查询
            answer = await self.rag_chain.ainvoke(question)
            response_time = time.time() - start_time

            # 获取检索到的源文档
            source_docs = self.retriever.invoke(question)

            return {
                "system": "Native RAG",
                "question": question,
                "answer": answer,
                "response_time": response_time,
                "source_count": len(source_docs),
                "sources": [
                    {
                        "content": doc.page_content[:150]
                        + ("..." if len(doc.page_content) > 150 else ""),
                        "metadata": doc.metadata,
                    }
                    for doc in source_docs
                ],
            }

        except Exception as e:
            return {
                "system": "Native RAG",
                "question": question,
                "answer": f"查询过程中发生错误: {str(e)}",
                "response_time": time.time() - start_time,
                "source_count": 0,
                "sources": [],
                "error": str(e),
            }


# ============================================
# 第五部分：Simplified Advanced RAG 系统
# ============================================


class AdvancedRAGSystem:
    """高级RAG系统 - 简化版，避免复杂的LangChain链问题"""

    def __init__(
        self,
        api_key: str = None,
        embedding_model: str = "text-embedding-v2",
        chat_model: str = "qwen-plus",
        persist_dir: str = "./chroma_db_advanced",
    ):

        print(f"\n🔧 初始化 Advanced RAG 系统...")

        # 初始化阿里云百炼客户端
        self.embeddings = QwenEmbeddings(api_key, embedding_model)
        self.llm = QwenChatLLM(api_key, chat_model)

        self.persist_dir = persist_dir
        self.vectorstore = None
        self.retriever = None

        print(f"✅ 使用模型: Embedding({embedding_model}), Chat({chat_model})")

    def build_knowledge_base(self, documents: List[Document]):
        """构建高级知识库"""
        print("\n🔨 构建 Advanced RAG 知识库...")
        print("  注: 正在调用真实的千问Embedding API")

        # 1. 创建向量存储
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_dir,
        )

        # 2. 创建检索器
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity", search_kwargs={"k": 6}
        )

        print(f"✅ Advanced RAG 知识库构建完成")
        print(f"   存储路径: {self.persist_dir}")

        return self

    async def query(self, question: str) -> Dict[str, Any]:
        """高级查询 - 包含查询优化"""
        if not self.retriever:
            raise ValueError("请先调用 build_knowledge_base() 构建知识库")

        print(f"\n🔍 Advanced RAG 查询: {question}")
        start_time = time.time()

        try:
            # 1. 查询优化
            optimized_query = await self._optimize_query(question)
            if optimized_query != question:
                print(f"  🔄 查询优化: {question} -> {optimized_query}")

            # 2. 检索文档
            source_docs = self.retriever.invoke(optimized_query)

            # 3. 构建上下文
            context = self._format_docs_with_metadata(source_docs)

            # 4. 生成回答
            prompt = self._create_prompt(context, question)
            answer = await self.llm.ainvoke(prompt)

            response_time = time.time() - start_time

            # 5. 计算置信度
            confidence = self._calculate_confidence(source_docs)

            return {
                "system": "Advanced RAG",
                "question": question,
                "optimized_query": (
                    optimized_query if optimized_query != question else None
                ),
                "answer": answer,
                "response_time": response_time,
                "confidence": confidence,
                "source_count": len(source_docs),
                "sources": [
                    {
                        "content": doc.page_content[:150]
                        + ("..." if len(doc.page_content) > 150 else ""),
                        "metadata": doc.metadata,
                    }
                    for doc in source_docs[:3]
                ],
            }

        except Exception as e:
            return {
                "system": "Advanced RAG",
                "question": question,
                "answer": f"查询过程中发生错误: {str(e)}",
                "response_time": time.time() - start_time,
                "confidence": 0.0,
                "source_count": 0,
                "sources": [],
                "error": str(e),
            }

    async def _optimize_query(self, query: str) -> str:
        """优化查询以获得更好检索结果"""
        try:
            # 直接调用LLM，避免复杂的LangChain链
            prompt = f"""请将以下查询优化为更适合信息检索的版本，保持原意但更具体。

原始查询: {query}

优化后的查询:"""

            optimized = await self.llm.ainvoke(prompt)
            return optimized.strip()
        except:
            return query

    def _format_docs_with_metadata(self, docs: List[Document]) -> str:
        """格式化文档并包含元数据"""
        formatted = []
        for i, doc in enumerate(docs, 1):
            source = doc.metadata.get("source", "未知")
            topic = doc.metadata.get("topic", "")
            content = doc.page_content

            formatted.append(
                f"[文档{i}] 来源: {source}\n" f"主题: {topic}\n" f"内容: {content}"
            )
        return "\n\n".join(formatted)

    def _create_prompt(self, context: str, question: str) -> str:
        """创建提示词"""
        return f"""你是一个专业的AI助手，请基于检索到的信息提供准确回答。

检索到的信息：
{context}

用户问题：
{question}

要求：
1. 严格基于检索到的信息回答
2. 如果信息不足，请明确说明"根据检索到的信息，无法完全回答此问题"
3. 回答要结构清晰、重点突出
4. 可以补充相关背景知识
5. 使用中文回答

专业回答："""

    def _calculate_confidence(self, docs: List[Document]) -> float:
        """计算回答置信度（基于检索结果）"""
        if not docs:
            return 0.0

        # 简单的置信度计算：基于文档数量和长度
        doc_factor = min(len(docs) / 5, 1.0)

        total_len = sum(len(doc.page_content) for doc in docs)
        avg_len = total_len / len(docs)
        len_factor = min(avg_len / 300, 1.0)

        confidence = 0.6 * doc_factor + 0.4 * len_factor
        return round(confidence, 3)


# ============================================
# 第六部分：主程序
# ============================================


async def main():
    """主函数 - 运行对比测试"""
    print("=" * 60)
    print("🚀 阿里云百炼 RAG 系统对比测试 (修复版)")
    print("解决了 ChatPromptValue 类型不兼容问题")
    print("=" * 60)

    # 1. 准备数据
    print("\n📚 准备测试数据...")
    processor = DocumentProcessor()
    sample_docs = processor.create_sample_documents()
    chunks = processor.split_documents(sample_docs)

    # 2. 初始化RAG系统
    print("\n🔧 初始化RAG系统...")
    native_rag = NativeRAGSystem(api_key=API_KEY)
    advanced_rag = AdvancedRAGSystem(api_key=API_KEY)

    # 3. 构建知识库
    native_rag.build_knowledge_base(chunks)
    advanced_rag.build_knowledge_base(chunks)

    # 4. 测试问题
    test_questions = [
        "如何获取阿里云百炼的API Key？",
        "RAG系统的基本架构是什么？",
        "LangChain 1.2.x有什么重要变化？",
    ]

    # 5. 运行对比测试
    print(f"\n🧪 开始运行 {len(test_questions)} 个测试问题...")
    print("=" * 60)

    all_results = []

    for i, question in enumerate(test_questions, 1):
        print(f"\n测试 {i}/{len(test_questions)}: {question}")
        print("-" * 40)

        # 运行Native RAG
        native_result = await native_rag.query(question)
        print(f"🔵 Native RAG:")
        print(f"   用时: {native_result['response_time']:.2f}s")
        print(f"   来源: {native_result['source_count']}个")
        print(f"   回答摘要: {native_result['answer'][:100]}...")

        # 运行Advanced RAG
        advanced_result = await advanced_rag.query(question)
        print(f"\n🟢 Advanced RAG:")
        print(f"   用时: {advanced_result['response_time']:.2f}s")
        print(f"   置信度: {advanced_result['confidence']:.1%}")
        print(f"   来源: {advanced_result['source_count']}个")
        if advanced_result.get("optimized_query"):
            print(f"   优化查询: {advanced_result['optimized_query']}")
        print(f"   回答摘要: {advanced_result['answer'][:100]}...")

        all_results.append(
            {"question": question, "native": native_result, "advanced": advanced_result}
        )

    # 6. 生成报告
    print(f"\n{'='*60}")
    print("📊 测试报告")
    print(f"{'='*60}")

    if all_results:
        native_times = [r["native"]["response_time"] for r in all_results]
        advanced_times = [r["advanced"]["response_time"] for r in all_results]
        native_sources = [r["native"]["source_count"] for r in all_results]
        advanced_sources = [r["advanced"]["source_count"] for r in all_results]

        print(f"\n📈 性能统计:")
        print(f"  Native RAG 平均响应时间: {np.mean(native_times):.2f}s")
        print(f"  Advanced RAG 平均响应时间: {np.mean(advanced_times):.2f}s")
        print(f"  Native RAG 平均来源数: {np.mean(native_sources):.1f}")
        print(f"  Advanced RAG 平均来源数: {np.mean(advanced_sources):.1f}")

        if HAS_NUMPY:
            time_improvement = (
                (np.mean(native_times) - np.mean(advanced_times))
                / np.mean(native_times)
                * 100
            )
            print(f"\n📈 性能提升:")
            print(f"  Advanced 比 Native 时间变化: {time_improvement:+.1f}%")

    # 7. 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"rag_comparison_fixed_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 详细结果已保存到: {filename}")

    return all_results


def quick_test():
    """快速测试阿里云百炼API连通性"""
    print("🔧 快速测试阿里云百炼API连通性...")

    try:
        # 测试Chat API
        response = Generation.call(
            api_key=API_KEY,
            model="qwen-plus",
            messages=[{"role": "user", "content": "你好，请用一句话介绍你自己。"}],
            result_format="message",
        )

        if response.status_code == 200:
            print(f"✅ Chat API 测试成功")
            print(f"   回复: {response.output.choices[0].message.content}")
        else:
            print(f"❌ Chat API 测试失败: {response.code} - {response.message}")

        # 测试Embedding API
        resp = TextEmbedding.call(model="text-embedding-v2", input="测试文本")

        if resp.status_code == 200:
            print(f"✅ Embedding API 测试成功")
            print(f"   向量维度: {len(resp.output['embeddings'][0]['embedding'])}")
        else:
            print(f"❌ Embedding API 测试失败: {resp.code} - {resp.message}")

    except Exception as e:
        print(f"❌ API测试异常: {e}")


# ============================================
# 脚本入口
# ============================================


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="阿里云百炼 RAG 系统 (修复版)")
    parser.add_argument("--test-api", action="store_true", help="测试API连通性")
    parser.add_argument("--run", action="store_true", help="运行完整对比测试")
    parser.add_argument("--quick", action="store_true", help="快速运行单个测试")
    parser.add_argument("--debug", action="store_true", help="调试模式，显示详细错误")

    args = parser.parse_args()

    if args.debug:
        import traceback

        traceback.format_exc = lambda: traceback.format_exc()

    if args.test_api:
        quick_test()
    elif args.run:
        asyncio.run(main())
    elif args.quick:
        # 快速演示
        print("🚀 快速演示模式...")
        processor = DocumentProcessor()
        docs = processor.create_sample_documents()[:2]
        chunks = processor.split_documents(docs)

        rag = NativeRAGSystem(api_key=API_KEY)
        rag.build_knowledge_base(chunks)

        result = asyncio.run(rag.query("什么是RAG系统？"))
        print(f"\n📋 查询结果:")
        print(f"问题: {result['question']}")
        print(f"回答: {result['answer']}")
        print(f"用时: {result['response_time']:.2f}s")
        print(f"来源: {result['source_count']}个")
    else:
        # 默认运行完整测试
        asyncio.run(main())
