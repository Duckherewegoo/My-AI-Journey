#!/usr/bin/env python3
"""
LangChain 1.2.x RAG 系统 - 使用正确的千问API调用方式
完全符合官方文档：https://help.aliyun.com/zh/model-studio/developer-reference/compatibility-of-openai-with-dashscope/
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib

# ============================================
# 第一部分：正确的 LangChain 1.2.x 模块导入
# ============================================

print("🔧 导入 LangChain 1.2.x 模块...")

try:
    # 1. 文本分割器 - 独立包
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    print("✅ langchain_text_splitters 导入成功")
except ImportError as e:
    print(f"❌ langchain_text_splitters 导入失败: {e}")
    print("请运行: pip install langchain-text-splitters")
    sys.exit(1)

try:
    # 2. 文档加载器 - 社区包
    from langchain_community.document_loaders import TextLoader, PyPDFLoader

    print("✅ langchain_community.document_loaders 导入成功")
except ImportError as e:
    print(f"❌ langchain_community.document_loaders 导入失败: {e}")
    sys.exit(1)

try:
    # 3. 核心模块
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.runnables import RunnablePassthrough, RunnableLambda

    print("✅ langchain_core 模块导入成功")
except ImportError as e:
    print(f"❌ langchain_core 导入失败: {e}")
    sys.exit(1)

try:
    # 4. 向量数据库 - Chroma集成
    from langchain_chroma import Chroma

    print("✅ langchain_chroma 导入成功")
except ImportError as e:
    print(f"❌ langchain_chroma 导入失败: {e}")
    sys.exit(1)

try:
    # 5. 关键：从langchain_classic导入检索器
    from langchain_classic.retrievers import (
        ContextualCompressionRetriever,
        EnsembleRetriever,
        BM25Retriever,
    )
    from langchain_classic.retrievers.document_compressors import LLMChainExtractor

    print("✅ langchain_classic.retrievers 导入成功")
except ImportError as e:
    print(f"❌ langchain_classic 导入失败: {e}")
    print("请运行: pip install langchain-classic")
    sys.exit(1)

# 6. 其他依赖
try:
    import chromadb
    import numpy as np
    from dotenv import load_dotenv

    print("✅ 其他依赖导入成功")
except ImportError as e:
    print(f"❌ 依赖导入失败: {e}")
    sys.exit(1)

# 7. 加载环境变量
load_dotenv()

# 8. 验证安装
import langchain

print(f"\n📦 LangChain 版本: {langchain.__version__}")
print("=" * 60)

# ============================================
# 第二部分：千问API客户端（完全正确的调用方式）
# ============================================


class QwenClient:
    """千问API客户端 - 完全按照官方文档实现"""

    def __init__(self, api_key: str = None, model: str = "qwen-plus"):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("未设置 DASHSCOPE_API_KEY 环境变量")

        self.model = model
        self.base_url = (
            "https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1"
        )

        # 导入OpenAI客户端
        from openai import OpenAI

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        print(f"✅ 千问API客户端初始化完成 (模型: {self.model})")

    def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """聊天补全 - 使用 client.responses.create"""
        try:
            # 构建输入文本
            input_text = ""
            for msg in messages:
                if msg["role"] == "user":
                    input_text = msg["content"]
                    break

            if not input_text:
                # 如果没有user消息，使用最后一个消息
                input_text = messages[-1]["content"] if messages else ""

            # 调用千问API
            response = self.client.responses.create(model=self.model, input=input_text)

            # 返回输出文本
            return response.output_text

        except Exception as e:
            error_msg = f"千问API调用失败: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg

    async def achat_completion(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """异步聊天补全"""
        # 这里使用同步调用，实际生产环境可以用异步客户端
        return self.chat_completion(messages, **kwargs)

    def generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入"""
        # 注意：千问API的Embedding调用方式不同
        # 这里使用一个简单的方法，实际应用中应该调用千问的Embedding API
        print(f"⚠️ 注意: 使用模拟的Embedding，实际应调用千问Embedding API")

        # 返回随机向量作为示例
        import random

        dimension = 1536  # OpenAI兼容的维度
        return [random.uniform(-1, 1) for _ in range(dimension)]


# ============================================
# 第三部分：自定义LangChain组件，适配千问API
# ============================================


class QwenLLM:
    """自定义LangChain LLM包装器，适配千问API"""

    def __init__(self, qwen_client: QwenClient, temperature: float = 0.1):
        self.qwen_client = qwen_client
        self.temperature = temperature

    def invoke(self, input_text: str) -> str:
        """同步调用"""
        messages = [{"role": "user", "content": input_text}]
        return self.qwen_client.chat_completion(messages)

    async def ainvoke(self, input_text: str) -> str:
        """异步调用"""
        messages = [{"role": "user", "content": input_text}]
        return await self.qwen_client.achat_completion(messages)

    def __call__(self, input_text: str) -> str:
        """调用操作符"""
        return self.invoke(input_text)


class QwenEmbeddings:
    """自定义Embeddings包装器，适配千问API"""

    def __init__(self, qwen_client: QwenClient):
        self.qwen_client = qwen_client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        return [self.qwen_client.generate_embedding(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        """嵌入查询"""
        return self.qwen_client.generate_embedding(text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """异步嵌入文档列表"""
        return self.embed_documents(texts)

    async def aembed_query(self, text: str) -> List[float]:
        """异步嵌入查询"""
        return self.embed_query(text)


# ============================================
# 第四部分：文档处理器
# ============================================


class DocumentProcessor:
    """文档处理器"""

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            add_start_index=True,
            is_separator_regex=False,
        )

    def load_documents(self, file_paths: List[str]) -> List[Document]:
        """加载文档"""
        all_docs = []

        for file_path in file_paths:
            path = Path(file_path)
            if not path.exists():
                print(f"⚠️ 文件不存在: {file_path}")
                continue

            try:
                if path.suffix.lower() in [".txt", ".md"]:
                    loader = TextLoader(str(path), encoding="utf-8")
                elif path.suffix.lower() == ".pdf":
                    loader = PyPDFLoader(str(path))
                else:
                    print(f"❌ 不支持的文件格式: {path.suffix}")
                    continue

                docs = loader.load()

                for i, doc in enumerate(docs):
                    doc.metadata.update(
                        {
                            "source": str(path),
                            "filename": path.name,
                            "file_type": path.suffix.lower(),
                            "doc_id": f"{path.stem}_{i}",
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                all_docs.extend(docs)
                print(f"✅ 已加载: {path.name} ({len(docs)}个文档)")

            except Exception as e:
                print(f"❌ 加载失败 {path.name}: {e}")

        return all_docs

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """分割文档"""
        if not documents:
            return []

        chunks = self.text_splitter.split_documents(documents)

        for i, chunk in enumerate(chunks):
            chunk.metadata.update(
                {
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "chunk_hash": hashlib.md5(chunk.page_content.encode()).hexdigest()[
                        :8
                    ],
                }
            )

        print(f"📊 文档分割完成: {len(documents)}个文档 → {len(chunks)}个chunks")
        return chunks

    def create_sample_data(self) -> List[Document]:
        """创建示例数据"""
        sample_data = [
            {
                "content": """千问API是阿里云提供的通义千问大模型服务。
                调用方式: 使用OpenAI SDK，但base_url要设置为 https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1
                使用client.responses.create()方法，而不是client.chat.completions.create()。""",
                "metadata": {"source": "qwen_api.txt", "topic": "API调用"},
            },
            {
                "content": """LangChain 1.2.x 中，模块结构发生了变化:
                1. 移除了 langchain.text_splitter，使用独立的 langchain_text_splitters
                2. 移除了 langchain.retrievers，相关功能移到 langchain_classic.retrievers
                3. 更模块化的设计，每个功能都有独立的包。""",
                "metadata": {"source": "langchain_changes.txt", "topic": "版本变化"},
            },
            {
                "content": """RAG系统架构包括四个核心组件:
                1. 文档加载和预处理
                2. 向量化存储和检索
                3. 查询处理和优化
                4. 生成和响应返回
                高级RAG会加入查询扩展、重排序、混合检索等技术。""",
                "metadata": {"source": "rag_architecture.txt", "topic": "RAG架构"},
            },
            {
                "content": """Chroma是一个开源的向量数据库，专为AI应用设计。
                支持多种嵌入模型，提供高效的相似性搜索。
                在RAG系统中，Chroma用于存储和检索文档的向量表示。""",
                "metadata": {"source": "chroma_db.txt", "topic": "向量数据库"},
            },
        ]

        documents = []
        for item in sample_data:
            doc = Document(page_content=item["content"], metadata=item["metadata"])
            documents.append(doc)

        return documents


# ============================================
# 第五部分：Native RAG 系统
# ============================================


class NativeRAGSystem:
    """Native RAG 系统 - 使用千问API"""

    def __init__(
        self,
        api_key: str = None,
        model: str = "qwen-plus",
        persist_directory: str = "./chroma_db_native_qwen",
    ):

        # 初始化千问客户端
        self.qwen_client = QwenClient(api_key=api_key, model=model)

        # 创建LangChain兼容的组件
        self.llm = QwenLLM(self.qwen_client)
        self.embeddings = QwenEmbeddings(self.qwen_client)

        self.persist_directory = persist_directory

        # 核心组件
        self.vectorstore = None
        self.retriever = None
        self.rag_chain = None

        print(f"✅ Native RAG 系统初始化完成 (使用千问API: {model})")

    def build_knowledge_base(self, documents: List[Document]) -> "NativeRAGSystem":
        """构建知识库"""
        print("\n🔨 构建 Native RAG 知识库...")

        # 创建向量存储
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_directory,
        )

        # 创建检索器
        self.retriever = self.vectorstore.as_retriever(
            search_type="similarity", search_kwargs={"k": 3}
        )

        # 构建RAG Chain
        self._build_rag_chain()

        print(f"✅ Native RAG 知识库构建完成: {len(documents)}个文档块")
        return self

    def _build_rag_chain(self):
        """构建RAG链"""
        template = """基于以下上下文信息回答问题：

上下文信息:
{context}

用户问题: 
{question}

如果上下文没有相关信息，请诚实地说"根据提供的上下文，我无法回答这个问题"。

请用中文提供准确、详细的回答:"""

        prompt = ChatPromptTemplate.from_template(template)

        def format_docs(docs: List[Document]) -> str:
            formatted = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get("source", "未知")
                content = doc.page_content
                formatted.append(f"[文档{i+1}] 来源: {source}\n内容: {content}")
            return "\n\n".join(formatted)

        # 构建Runnable链
        self.rag_chain = (
            {"context": self.retriever | format_docs, "question": RunnablePassthrough()}
            | prompt
            | self.llm
            | StrOutputParser()
        )

    async def query_async(self, question: str) -> Dict[str, Any]:
        """异步查询"""
        if not self.rag_chain:
            raise ValueError("请先构建知识库")

        start_time = time.time()

        try:
            # 执行查询
            answer = await self.rag_chain.ainvoke(question)
            response_time = time.time() - start_time

            # 获取源文档
            relevant_docs = self.retriever.invoke(question)

            # 整理源文档信息
            sources = []
            for doc in relevant_docs:
                sources.append(
                    {
                        "content": doc.page_content[:200]
                        + ("..." if len(doc.page_content) > 200 else ""),
                        "metadata": doc.metadata,
                    }
                )

            return {
                "system_name": "Native RAG",
                "question": question,
                "answer": answer,
                "response_time": response_time,
                "source_count": len(relevant_docs),
                "sources": sources,
            }

        except Exception as e:
            return {
                "system_name": "Native RAG",
                "question": question,
                "answer": f"查询失败: {str(e)}",
                "response_time": time.time() - start_time,
                "source_count": 0,
                "sources": [],
                "error": str(e),
            }

    def query(self, question: str) -> Dict[str, Any]:
        """同步查询"""
        return asyncio.run(self.query_async(question))


# ============================================
# 第六部分：Advanced RAG 系统
# ============================================


class AdvancedRAGSystem:
    """Advanced RAG 系统 - 使用千问API + langchain_classic高级功能"""

    def __init__(
        self,
        api_key: str = None,
        model: str = "qwen-plus",
        persist_directory: str = "./chroma_db_advanced_qwen",
    ):

        # 初始化千问客户端
        self.qwen_client = QwenClient(api_key=api_key, model=model)

        # 创建LangChain兼容的组件
        self.llm = QwenLLM(self.qwen_client)
        self.embeddings = QwenEmbeddings(self.qwen_client)

        self.persist_directory = persist_directory

        # 核心组件
        self.vectorstore = None
        self.retriever = None
        self.rag_pipeline = None

        print(f"✅ Advanced RAG 系统初始化完成 (使用千问API: {model})")

    def build_knowledge_base(self, documents: List[Document]) -> "AdvancedRAGSystem":
        """构建高级知识库"""
        print("\n🔨 构建 Advanced RAG 知识库 (使用langchain_classic)...")

        # 1. 创建向量存储
        self.vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_directory,
        )

        # 2. 创建基础向量检索器
        vector_retriever = self.vectorstore.as_retriever(
            search_type="similarity", search_kwargs={"k": 10}
        )

        # 3. 使用 langchain_classic 创建高级检索器
        try:
            # 创建BM25关键词检索器
            bm25_retriever = BM25Retriever.from_documents(documents)
            bm25_retriever.k = 5

            # 创建混合检索器 (向量 + 关键词)
            ensemble_retriever = EnsembleRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                weights=[0.7, 0.3],  # 70%向量, 30%关键词
            )

            # 创建上下文压缩
            compressor = LLMChainExtractor.from_llm(self.llm)

            # 最终检索器
            self.retriever = ContextualCompressionRetriever(
                base_compressor=compressor, base_retriever=ensemble_retriever
            )

            print("✅ 使用 langchain_classic 高级检索器")

        except Exception as e:
            print(f"⚠️ 创建高级检索器失败: {e}")
            print("使用基础向量检索器")
            self.retriever = vector_retriever

        # 4. 构建RAG pipeline
        self._build_rag_pipeline()

        print("✅ Advanced RAG 知识库构建完成")
        return self

    def _build_rag_pipeline(self):
        """构建高级RAG pipeline"""

        # 查询重写函数
        async def rewrite_query(query: str) -> str:
            """优化查询以获得更好的检索结果"""
            rewrite_prompt = ChatPromptTemplate.from_template(
                "请优化以下查询，使其更适合信息检索。保持原意。\n\n原始查询: {query}\n优化后查询:"
            )

            rewrite_chain = rewrite_prompt | self.llm | StrOutputParser()

            try:
                rewritten = await rewrite_chain.ainvoke({"query": query})
                return rewritten.strip()
            except:
                return query

        # 完整的RAG pipeline
        async def full_pipeline(question: str) -> Dict[str, Any]:
            """完整的RAG处理流程"""
            # 1. 查询优化
            optimized_query = await rewrite_query(question)
            if optimized_query != question:
                print(f"  🔄 查询优化: {question} -> {optimized_query}")

            # 2. 检索文档
            docs = self.retriever.invoke(optimized_query)

            # 3. 格式化上下文
            context_parts = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get("source", "未知")
                topic = doc.metadata.get("topic", "")
                content = doc.page_content

                context_parts.append(
                    f"[信息{i+1}] 来源: {source}\n"
                    f"主题: {topic}\n"
                    f"内容: {content}"
                )

            context = "\n\n".join(context_parts)

            # 4. 构建prompt
            template = """你是一个专业的AI助手，请基于检索到的信息提供准确回答。

检索到的信息:
{context}

用户问题: 
{question}

回答要求:
1. 严格基于检索到的信息
2. 如果信息不足，请明确说明
3. 回答要结构清晰、重点突出
4. 可以补充相关背景知识
5. 使用中文回答

专业回答:"""

            prompt = ChatPromptTemplate.from_template(template)

            # 5. 生成回答
            chain = prompt | self.llm | StrOutputParser()
            answer = await chain.ainvoke({"context": context, "question": question})

            return {"answer": answer, "optimized_query": optimized_query, "docs": docs}

        self.rag_pipeline = full_pipeline

    async def query_async(self, question: str) -> Dict[str, Any]:
        """异步查询"""
        if not self.rag_pipeline:
            raise ValueError("请先构建知识库")

        start_time = time.time()

        try:
            # 执行完整的RAG pipeline
            result = await self.rag_pipeline(question)
            response_time = time.time() - start_time

            # 计算置信度
            confidence = self._calculate_confidence(result["docs"])

            # 整理源文档信息
            sources = []
            for doc in result["docs"]:
                sources.append(
                    {
                        "content": doc.page_content[:200]
                        + ("..." if len(doc.page_content) > 200 else ""),
                        "metadata": doc.metadata,
                    }
                )

            return {
                "system_name": "Advanced RAG",
                "question": question,
                "answer": result["answer"],
                "response_time": response_time,
                "source_count": len(result["docs"]),
                "sources": sources,
                "confidence": confidence,
                "optimized_query": result.get("optimized_query", question),
            }

        except Exception as e:
            return {
                "system_name": "Advanced RAG",
                "question": question,
                "answer": f"查询失败: {str(e)}",
                "response_time": time.time() - start_time,
                "source_count": 0,
                "sources": [],
                "error": str(e),
            }

    def _calculate_confidence(self, docs: List[Document]) -> float:
        """计算回答置信度"""
        if not docs:
            return 0.0

        # 简单实现：基于文档数量和内容长度
        doc_count_factor = min(len(docs) / 5, 1.0)  # 最多5个文档

        total_length = sum(len(doc.page_content) for doc in docs)
        avg_length = total_length / len(docs) if docs else 0
        length_factor = min(avg_length / 500, 1.0)  # 平均长度不超过500字符

        confidence = doc_count_factor * 0.6 + length_factor * 0.4
        return round(confidence, 2)

    def query(self, question: str) -> Dict[str, Any]:
        """同步查询"""
        return asyncio.run(self.query_async(question))


# ============================================
# 第七部分：对比测试
# ============================================


async def run_comparison_test():
    """运行对比测试"""
    print("\n" + "=" * 60)
    print("🚀 LangChain 1.2.x RAG 系统对比测试")
    print("使用完全正确的千问API调用方式")
    print("=" * 60)

    # 检查API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("⚠️ 警告: 未设置 DASHSCOPE_API_KEY 环境变量")
        print("请设置环境变量: export DASHSCOPE_API_KEY=your-key-here")
        return

    # 1. 创建文档处理器
    processor = DocumentProcessor(chunk_size=400, chunk_overlap=50)

    # 2. 准备数据
    print("\n📚 准备数据...")
    documents = processor.create_sample_data()
    chunks = processor.split_documents(documents)

    # 3. 初始化RAG系统
    print("\n🔧 初始化RAG系统...")
    native_rag = NativeRAGSystem(api_key=api_key, model="qwen-plus")
    advanced_rag = AdvancedRAGSystem(api_key=api_key, model="qwen-plus")

    native_rag.build_knowledge_base(chunks)
    advanced_rag.build_knowledge_base(chunks)

    # 4. 测试问题
    test_questions = [
        "千问API如何调用？",
        "LangChain 1.2.x有什么变化？",
        "什么是RAG系统？",
    ]

    # 5. 运行测试
    all_results = []

    for i, question in enumerate(test_questions, 1):
        print(f"\n{'='*60}")
        print(f"🧪 测试 {i}/{len(test_questions)}: {question}")
        print(f"{'='*60}")

        # Native RAG
        print("\n🔵 Native RAG 查询中...")
        native_result = await native_rag.query_async(question)

        print(f"   用时: {native_result['response_time']:.2f}s")
        print(f"   来源: {native_result['source_count']}个")
        print(f"   回答: {native_result['answer'][:150]}...")

        # Advanced RAG
        print("\n🟢 Advanced RAG 查询中...")
        advanced_result = await advanced_rag.query_async(question)

        print(f"   用时: {advanced_result['response_time']:.2f}s")
        print(f"   置信度: {advanced_result.get('confidence', 0):.1%}")
        print(f"   来源: {advanced_result['source_count']}个")
        if advanced_result.get("optimized_query") != question:
            print(f"   优化查询: {advanced_result['optimized_query']}")
        print(f"   回答: {advanced_result['answer'][:150]}...")

        all_results.append(
            {"question": question, "native": native_result, "advanced": advanced_result}
        )

    # 6. 生成报告
    print(f"\n{'='*60}")
    print("📊 测试报告")
    print(f"{'='*60}")

    native_times = []
    advanced_times = []
    native_sources = []
    advanced_sources = []

    for result in all_results:
        native_times.append(result["native"]["response_time"])
        advanced_times.append(result["advanced"]["response_time"])
        native_sources.append(result["native"]["source_count"])
        advanced_sources.append(result["advanced"]["source_count"])

    print(f"\n📈 性能统计:")
    print(f"  Native RAG 平均响应时间: {np.mean(native_times):.2f}s")
    print(f"  Advanced RAG 平均响应时间: {np.mean(advanced_times):.2f}s")
    print(f"  Native RAG 平均来源数: {np.mean(native_sources):.1f}")
    print(f"  Advanced RAG 平均来源数: {np.mean(advanced_sources):.1f}")

    # 7. 保存结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"rag_test_results_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n💾 测试结果已保存到: {filename}")

    return all_results


# ============================================
# 第八部分：命令行工具
# ============================================


def test_qwen_api():
    """测试千问API连接"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 未设置 DASHSCOPE_API_KEY 环境变量")
        return False

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/api/v2/apps/protocols/compatible-mode/v1",
        )

        print("🔧 测试千问API连接...")
        response = client.responses.create(
            model="qwen-plus", input="你好，请简单介绍一下你自己"
        )

        print(f"✅ API连接成功!")
        print(f"🤖 模型回复: {response.output_text}")
        return True

    except Exception as e:
        print(f"❌ API连接失败: {e}")
        return False


def interactive_mode():
    """交互模式"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("❌ 未设置 DASHSCOPE_API_KEY 环境变量")
        print("请设置: export DASHSCOPE_API_KEY=your-key-here")
        return

    print("\n" + "=" * 60)
    print("🤖 千问API RAG 交互模式")
    print("=" * 60)

    # 初始化系统
    processor = DocumentProcessor()
    documents = processor.create_sample_data()
    chunks = processor.split_documents(documents)

    print("\n请选择RAG系统类型:")
    print("1. Native RAG (基础)")
    print("2. Advanced RAG (高级)")

    choice = input("\n请选择 (1-2): ").strip()

    if choice == "1":
        rag_system = NativeRAGSystem(api_key=api_key)
    elif choice == "2":
        rag_system = AdvancedRAGSystem(api_key=api_key)
    else:
        print("❌ 无效选择")
        return

    # 构建知识库
    rag_system.build_knowledge_base(chunks)

    # 交互循环
    print("\n💬 开始交互 (输入 'quit' 退出)")
    print("-" * 40)

    while True:
        question = input("\n❓ 请输入问题: ").strip()

        if question.lower() in ["quit", "exit", "q"]:
            print("👋 再见!")
            break

        if not question:
            continue

        print("🔍 查询中...")

        try:
            if choice == "1":
                result = rag_system.query(question)
            else:
                result = rag_system.query(question)

            print(f"\n✅ 回答:")
            print(f"{result['answer']}")
            print(f"\n⏱️  用时: {result['response_time']:.2f}s")
            print(f"📚 来源文档: {result['source_count']}个")

            if "confidence" in result:
                print(f"📊 置信度: {result['confidence']:.1%}")

            # 显示来源
            if result["sources"]:
                print(f"\n🔍 相关来源:")
                for i, source in enumerate(result["sources"][:3], 1):
                    print(f"  {i}. {source['content'][:100]}...")

        except Exception as e:
            print(f"❌ 查询失败: {e}")


# ============================================
# 第九部分：主程序
# ============================================


def main():
    """主程序"""
    print("=" * 60)
    print("🚀 LangChain 1.2.x RAG 系统 (千问API版本)")
    print("=" * 60)

    # 检查命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "--test-api":
            test_qwen_api()
        elif sys.argv[1] == "--interactive":
            interactive_mode()
        elif sys.argv[1] == "--run-test":
            asyncio.run(run_comparison_test())
        elif sys.argv[1] == "--help":
            print("""
            使用方法:
              python qwen_rag.py                     # 主菜单
              python qwen_rag.py --test-api          # 测试API连接
              python qwen_rag.py --interactive       # 交互模式
              python qwen_rag.py --run-test          # 运行对比测试
              python qwen_rag.py --help              # 显示帮助
            
            环境变量:
              需要设置 DASHSCOPE_API_KEY
              示例: export DASHSCOPE_API_KEY=your-key-here
            
            注意:
              1. 使用完全正确的千问API调用方式
              2. 使用正确的LangChain 1.2.x模块结构
              3. 需要安装 langchain-classic 以使用高级检索器
            """)
        else:
            print(f"❌ 未知参数: {sys.argv[1]}")
            print("使用 --help 查看帮助")
    else:
        # 显示主菜单
        print("\n📋 主菜单:")
        print("  1. 测试千问API连接")
        print("  2. 交互模式")
        print("  3. 运行对比测试")
        print("  4. 退出")

        choice = input("\n请选择 (1-4): ").strip()

        if choice == "1":
            test_qwen_api()
        elif choice == "2":
            interactive_mode()
        elif choice == "3":
            asyncio.run(run_comparison_test())
        elif choice == "4":
            print("👋 再见!")
        else:
            print("❌ 无效选择")


# ============================================
# 第十部分：脚本入口
# ============================================

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback

        traceback.print_exc()
