#!/usr/bin/env python3
"""
LangChain 1.2.x Native RAG vs Advanced RAG 实现
使用完全正确的模块结构：
- langchain_text_splitters (不是 langchain.text_splitter)
- langchain_classic.retrievers (不是 langchain.retrievers)
"""

import langchain
import os
import sys
import asyncio
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
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
    # 5. OpenAI集成 (用于DashScope)
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    print("✅ langchain_openai 导入成功")
except ImportError as e:
    print(f"❌ langchain_openai 导入失败: {e}")
    sys.exit(1)

try:
    # 6. 关键：从langchain_classic导入检索器
    from langchain_classic.retrievers import (
        ContextualCompressionRetriever,
        EnsembleRetriever,
        BM25Retriever,
        MultiQueryRetriever,
    )
    from langchain_classic.retrievers.document_compressors import LLMChainExtractor

    print("✅ langchain_classic.retrievers 导入成功")
except ImportError as e:
    print(f"❌ langchain_classic 导入失败: {e}")
    print("请运行: pip install langchain-classic")
    sys.exit(1)

# 其他依赖
try:
    import chromadb
    import numpy as np
    from dotenv import load_dotenv

    print("✅ 其他依赖导入成功")
except ImportError as e:
    print(f"❌ 依赖导入失败: {e}")
    sys.exit(1)

# 加载环境变量
load_dotenv()

# 验证安装
print(f"\n📦 LangChain 版本: {langchain.__version__}")
print("=" * 60)

# ============================================
# 第二部分：数据模型
# ============================================


@dataclass
class QueryResult:
    """查询结果数据类"""

    system_name: str
    question: str
    answer: str
    response_time: float
    source_count: int
    sources: List[Dict[str, Any]]
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def display_summary(self) -> str:
        """显示摘要"""
        if self.error:
            return f"[{self.system_name}] ❌ 错误: {self.error}"

        confidence_str = (
            f" (置信度: {self.confidence:.1%})" if self.confidence > 0 else ""
        )
        return (
            f"[{self.system_name}] ✅ 用时: {self.response_time:.2f}s{confidence_str}\n"
            f"    回答: {self.answer[:100]}..."
        )


# ============================================
# 第三部分：文档处理器
# ============================================


class DocumentProcessor:
    """文档处理器 - 使用正确的模块"""

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
                "content": """LangChain 1.2.x 是最新的LLM应用框架。
                重要变化: 1) 移除了 langchain.text_splitter，使用 langchain_text_splitters
                2) 移除了 langchain.retrievers，使用 langchain_classic.retrievers
                3) 更模块化的包结构，更好的类型提示。""",
                "metadata": {"source": "langchain_changes.txt", "topic": "版本变化"},
            },
            {
                "content": """RAG (检索增强生成) 系统架构包括:
                1. 文档加载: 从各种格式加载文档
                2. 文本分割: 将文档切分为小块
                3. 向量化: 将文本转换为向量嵌入
                4. 检索: 从向量数据库中检索相关文档
                5. 生成: 基于检索到的文档生成回答。""",
                "metadata": {"source": "rag_architecture.txt", "topic": "RAG架构"},
            },
            {
                "content": """Native RAG 使用基础的向量检索和生成。
                Advanced RAG 使用高级技术如:
                1. 查询扩展: 生成多个相关查询
                2. 混合检索: 结合向量检索和关键词检索
                3. 重排序: 对检索结果进行重新排序
                4. 上下文压缩: 压缩检索到的文档。""",
                "metadata": {"source": "advanced_rag.txt", "topic": "高级RAG"},
            },
            {
                "content": """Chroma 是一个开源的向量数据库，常用于RAG系统。
                在LangChain 1.2.x中，通过 langchain_chroma 包集成。
                支持持久化存储、多种距离度量、高效的相似性搜索。""",
                "metadata": {"source": "chroma_db.txt", "topic": "向量数据库"},
            },
            {
                "content": """DashScope API 是阿里云的通义千问API服务。
                在LangChain中可以通过 langchain_openai 兼容模式调用。
                支持Qwen系列模型，如 qwen-plus、qwen-max 等。""",
                "metadata": {"source": "dashscope.txt", "topic": "API服务"},
            },
        ]

        documents = []
        for item in sample_data:
            doc = Document(page_content=item["content"], metadata=item["metadata"])
            documents.append(doc)

        return documents


# ============================================
# 第四部分：Native RAG 系统
# ============================================


class NativeRAGSystem:
    """Native RAG 系统 - 使用基础功能"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        persist_directory: str = "./chroma_db_native",
    ):

        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            print("⚠️ 警告: 未设置 DASHSCOPE_API_KEY")
            print("请设置环境变量: export DASHSCOPE_API_KEY=your-key")

        self.base_url = base_url
        self.persist_directory = persist_directory

        # 初始化模型
        self.embeddings = self._create_embeddings()
        self.llm = self._create_llm()

        # 核心组件
        self.vectorstore = None
        self.retriever = None
        self.rag_chain = None

        print(f"✅ Native RAG 系统初始化完成")

    def _create_embeddings(self):
        """创建嵌入模型"""
        return OpenAIEmbeddings(
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            model="text-embedding-v2",
        )

    def _create_llm(self):
        """创建LLM"""
        return ChatOpenAI(
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            model_name="qwen-plus",
            temperature=0.1,
            max_tokens=1000,
        )

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

    async def query_async(self, question: str) -> QueryResult:
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

            return QueryResult(
                system_name="Native RAG",
                question=question,
                answer=answer,
                response_time=response_time,
                source_count=len(relevant_docs),
                sources=sources,
            )

        except Exception as e:
            return QueryResult(
                system_name="Native RAG",
                question=question,
                answer=f"查询失败: {str(e)}",
                response_time=time.time() - start_time,
                source_count=0,
                sources=[],
                error=str(e),
            )

    def query(self, question: str) -> QueryResult:
        """同步查询"""
        return asyncio.run(self.query_async(question))


# ============================================
# 第五部分：Advanced RAG 系统
# ============================================


class AdvancedRAGSystem:
    """Advanced RAG 系统 - 使用 langchain_classic 高级功能"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        persist_directory: str = "./chroma_db_advanced",
    ):

        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            print("⚠️ 警告: 未设置 DASHSCOPE_API_KEY")

        self.base_url = base_url
        self.persist_directory = persist_directory

        # 初始化模型
        self.embeddings = self._create_embeddings()
        self.llm = self._create_llm()

        # 核心组件
        self.vectorstore = None
        self.retriever = None
        self.rag_chain = None

        print(f"✅ Advanced RAG 系统初始化完成")

    def _create_embeddings(self):
        """创建嵌入模型"""
        return OpenAIEmbeddings(
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            model="text-embedding-v2",
        )

    def _create_llm(self):
        """创建LLM"""
        return ChatOpenAI(
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
            model_name="qwen-plus",
            temperature=0.1,
            max_tokens=1000,
        )

    def build_knowledge_base(self, documents: List[Document]) -> "AdvancedRAGSystem":
        """构建高级知识库"""
        print("\n🔨 构建 Advanced RAG 知识库 (使用 langchain_classic)...")

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

            print(
                "✅ 使用 langchain_classic 高级检索器: ContextualCompressionRetriever + EnsembleRetriever"
            )

        except Exception as e:
            print(f"⚠️ 创建高级检索器失败: {e}")
            print("使用基础向量检索器")
            self.retriever = vector_retriever

        # 4. 构建RAG链
        self._build_rag_chain()

        print("✅ Advanced RAG 知识库构建完成")
        return self

    def _build_rag_chain(self):
        """构建高级RAG链"""
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

        def format_docs(docs: List[Document]) -> str:
            formatted = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get("source", "未知")
                topic = doc.metadata.get("topic", "")
                content = doc.page_content

                formatted.append(
                    f"[信息{i+1}] 来源: {source}\n"
                    f"主题: {topic}\n"
                    f"内容: {content}"
                )
            return "\n\n".join(formatted)

        # 查询重写函数
        async def rewrite_query(query: str) -> str:
            """优化查询以获得更好的检索结果"""
            rewrite_template = ChatPromptTemplate.from_template(
                "请优化以下查询，使其更适合信息检索。保持原意。\n\n原始查询: {query}\n优化后查询:"
            )

            rewrite_chain = rewrite_template | self.llm | StrOutputParser()

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
            context = format_docs(docs)

            # 4. 生成回答
            chain = prompt | self.llm | StrOutputParser()
            answer = await chain.ainvoke({"context": context, "question": question})

            return {"answer": answer, "optimized_query": optimized_query, "docs": docs}

        self.rag_pipeline = full_pipeline

    async def query_async(self, question: str) -> QueryResult:
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

            return QueryResult(
                system_name="Advanced RAG",
                question=question,
                answer=result["answer"],
                response_time=response_time,
                source_count=len(result["docs"]),
                sources=sources,
                confidence=confidence,
            )

        except Exception as e:
            return QueryResult(
                system_name="Advanced RAG",
                question=question,
                answer=f"查询失败: {str(e)}",
                response_time=time.time() - start_time,
                source_count=0,
                sources=[],
                error=str(e),
            )

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

    def query(self, question: str) -> QueryResult:
        """同步查询"""
        return asyncio.run(self.query_async(question))


# ============================================
# 第六部分：对比测试系统
# ============================================


class RAGBenchmark:
    """RAG系统对比测试"""

    def __init__(self, native_rag: NativeRAGSystem, advanced_rag: AdvancedRAGSystem):
        self.native_rag = native_rag
        self.advanced_rag = advanced_rag
        self.test_history = []

    async def run_single_test(self, question: str) -> Dict[str, Any]:
        """运行单个测试"""
        print(f"\n{'='*60}")
        print(f"🧪 测试问题: {question}")
        print(f"{'='*60}")

        # 同时运行两个查询
        native_task = asyncio.create_task(self.native_rag.query_async(question))
        advanced_task = asyncio.create_task(self.advanced_rag.query_async(question))

        # 等待结果
        native_result = await native_task
        advanced_result = await advanced_task

        # 显示结果
        print(native_result.display_summary())
        print(advanced_result.display_summary())

        # 记录历史
        test_result = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "native": native_result.to_dict(),
            "advanced": advanced_result.to_dict(),
        }
        self.test_history.append(test_result)

        return test_result

    def run_batch_tests(self, questions: List[str]) -> List[Dict[str, Any]]:
        """批量运行测试"""
        print(f"\n{'='*60}")
        print(f"🚀 开始批量测试 ({len(questions)}个问题)")
        print(f"{'='*60}")

        results = []

        for i, question in enumerate(questions, 1):
            print(f"\n[{i}/{len(questions)}] ", end="")
            result = asyncio.run(self.run_single_test(question))
            results.append(result)

        return results

    def generate_report(self) -> str:
        """生成测试报告"""
        if not self.test_history:
            return "暂无测试数据"

        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("📊 RAG 系统测试报告")
        report_lines.append("=" * 60)

        # 计算统计信息
        native_times = []
        advanced_times = []
        native_sources = []
        advanced_sources = []

        for test in self.test_history:
            native_times.append(test["native"]["response_time"])
            advanced_times.append(test["advanced"]["response_time"])
            native_sources.append(test["native"]["source_count"])
            advanced_sources.append(test["advanced"]["source_count"])

        # 添加统计信息
        report_lines.append("\n📈 性能统计:")
        report_lines.append(f"  Native RAG 平均响应时间: {np.mean(native_times):.2f}s")
        report_lines.append(
            f"  Advanced RAG 平均响应时间: {np.mean(advanced_times):.2f}s"
        )
        report_lines.append(f"  Native RAG 平均来源数: {np.mean(native_sources):.1f}")
        report_lines.append(
            f"  Advanced RAG 平均来源数: {np.mean(advanced_sources):.1f}"
        )

        # 添加详细结果
        report_lines.append("\n📋 详细结果:")
        for i, test in enumerate(self.test_history, 1):
            report_lines.append(f"\n[{i}] 问题: {test['question']}")
            report_lines.append(
                f"    Native RAG: {test['native']['response_time']:.2f}s, {test['native']['source_count']}个来源"
            )
            report_lines.append(
                f"    Advanced RAG: {test['advanced']['response_time']:.2f}s, {test['advanced']['source_count']}个来源"
            )

        return "\n".join(report_lines)


# ============================================
# 第七部分：命令行界面
# ============================================


def clear_screen():
    """清屏"""
    os.system("cls" if os.name == "nt" else "clear")


def print_banner():
    """打印横幅"""
    banner = """
    ╔═══════════════════════════════════════════════════╗
    ║        LangChain 1.2.x RAG 系统对比测试           ║
    ║        Native RAG vs Advanced RAG                 ║
    ║        (使用正确的模块结构)                       ║
    ╚═══════════════════════════════════════════════════╝
    """
    print(banner)


def interactive_mode():
    """交互模式"""
    clear_screen()
    print_banner()

    print("\n🚀 初始化系统...")

    # 1. 创建文档处理器
    processor = DocumentProcessor(chunk_size=400, chunk_overlap=50)

    # 2. 准备数据
    print("\n📚 准备数据...")
    documents = processor.create_sample_data()
    chunks = processor.split_documents(documents)

    # 3. 初始化RAG系统
    print("\n🔧 初始化RAG系统...")
    native_rag = NativeRAGSystem()
    advanced_rag = AdvancedRAGSystem()

    native_rag.build_knowledge_base(chunks)
    advanced_rag.build_knowledge_base(chunks)

    # 4. 创建对比测试器
    benchmark = RAGBenchmark(native_rag, advanced_rag)

    # 5. 交互循环
    while True:
        print("\n" + "=" * 60)
        print("📋 菜单:")
        print("  1. 输入问题测试")
        print("  2. 运行预设测试")
        print("  3. 查看测试报告")
        print("  4. 退出")
        print("=" * 60)

        choice = input("\n请选择 (1-4): ").strip()

        if choice == "1":
            # 输入问题测试
            question = input("\n请输入问题: ").strip()
            if question:
                asyncio.run(benchmark.run_single_test(question))
            else:
                print("⚠️ 问题不能为空")

        elif choice == "2":
            # 运行预设测试
            preset_questions = [
                "LangChain 1.2.x有什么变化？",
                "什么是RAG系统？",
                "Advanced RAG有哪些高级技术？",
                "Chroma是什么？有什么作用？",
                "如何调用DashScope API？",
            ]

            confirm = input(
                f"\n将运行{len(preset_questions)}个预设问题，是否继续？(y/n): "
            ).lower()
            if confirm == "y":
                benchmark.run_batch_tests(preset_questions)

        elif choice == "3":
            # 查看测试报告
            report = benchmark.generate_report()
            print(report)

            # 保存报告
            save = input("\n是否保存报告到文件？(y/n): ").lower()
            if save == "y":
                filename = (
                    f"rag_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                )
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(report)
                print(f"✅ 报告已保存到: {filename}")

        elif choice == "4":
            print("\n👋 感谢使用，再见！")
            break

        else:
            print("⚠️ 无效选择，请重试")

        input("\n按回车键继续...")


# ============================================
# 第八部分：主程序
# ============================================


async def main_async():
    """异步主函数"""
    print_banner()

    # 检查API密钥
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("⚠️ 警告: 未设置 DASHSCOPE_API_KEY 环境变量")
        print("请设置环境变量或稍后在代码中配置")
        print("示例: export DASHSCOPE_API_KEY=your-key-here")
        confirm = input("\n是否继续？(y/n): ").lower()
        if confirm != "y":
            return

    # 运行模式选择
    print("\n📋 运行模式:")
    print("  1. 交互模式 (命令行界面)")
    print("  2. 快速演示 (运行预设测试)")
    print("  3. 单次测试")

    mode = input("\n请选择模式 (1-3): ").strip()

    # 初始化系统
    print("\n🚀 初始化系统...")

    # 1. 创建文档处理器
    processor = DocumentProcessor(chunk_size=400, chunk_overlap=50)

    # 2. 准备数据
    print("\n📚 准备数据...")
    documents = processor.create_sample_data()
    chunks = processor.split_documents(documents)

    # 3. 初始化RAG系统
    print("\n🔧 初始化RAG系统...")
    native_rag = NativeRAGSystem(api_key=api_key)
    advanced_rag = AdvancedRAGSystem(api_key=api_key)

    native_rag.build_knowledge_base(chunks)
    advanced_rag.build_knowledge_base(chunks)

    # 4. 创建对比测试器
    benchmark = RAGBenchmark(native_rag, advanced_rag)

    if mode == "1":
        # 交互模式
        while True:
            print("\n" + "=" * 60)
            print("📋 菜单:")
            print("  1. 输入问题测试")
            print("  2. 运行预设测试")
            print("  3. 查看测试报告")
            print("  4. 退出")
            print("=" * 60)

            choice = input("\n请选择 (1-4): ").strip()

            if choice == "1":
                question = input("\n请输入问题: ").strip()
                if question:
                    await benchmark.run_single_test(question)
                else:
                    print("⚠️ 问题不能为空")

            elif choice == "2":
                preset_questions = [
                    "LangChain 1.2.x有什么变化？",
                    "什么是RAG系统？",
                    "Advanced RAG有哪些高级技术？",
                    "Chroma是什么？有什么作用？",
                    "如何调用DashScope API？",
                ]

                print(f"\n运行{len(preset_questions)}个预设问题...")
                benchmark.run_batch_tests(preset_questions)

            elif choice == "3":
                report = benchmark.generate_report()
                print("\n" + report)

            elif choice == "4":
                print("\n👋 感谢使用，再见！")
                break

            else:
                print("⚠️ 无效选择")

    elif mode == "2":
        # 快速演示
        preset_questions = [
            "LangChain 1.2.x有什么变化？",
            "什么是RAG系统？",
            "Advanced RAG有哪些高级技术？",
        ]

        print(f"\n🚀 快速演示: 运行{len(preset_questions)}个测试问题")
        print("=" * 60)

        benchmark.run_batch_tests(preset_questions)

        # 生成报告
        report = benchmark.generate_report()
        print("\n" + report)

        # 保存报告
        filename = f"rag_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ 报告已保存到: {filename}")

    elif mode == "3":
        # 单次测试
        question = input("\n请输入测试问题: ").strip()
        if question:
            await benchmark.run_single_test(question)
        else:
            print("⚠️ 问题不能为空")

    else:
        print("⚠️ 无效模式选择")


def main():
    """主函数入口"""
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        print("\n\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")
        import traceback

        traceback.print_exc()


# ============================================
# 第九部分：直接运行示例
# ============================================


def quick_demo():
    """快速演示函数，可以直接调用"""
    print_banner()
    print("\n🚀 快速演示模式...")

    # 1. 创建文档处理器
    processor = DocumentProcessor()

    # 2. 准备数据
    documents = processor.create_sample_data()
    chunks = processor.split_documents(documents)

    # 3. 初始化RAG系统
    native_rag = NativeRAGSystem()
    advanced_rag = AdvancedRAGSystem()

    native_rag.build_knowledge_base(chunks)
    advanced_rag.build_knowledge_base(chunks)

    # 4. 测试问题
    test_questions = ["LangChain 1.2.x有什么变化？", "什么是RAG系统？"]

    # 5. 运行测试
    for question in test_questions:
        print(f"\n{'='*60}")
        print(f"🧪 测试: {question}")

        # Native RAG
        native_result = native_rag.query(question)
        print(f"\n🔵 Native RAG:")
        print(f"   用时: {native_result.response_time:.2f}s")
        print(f"   来源: {native_result.source_count}个")
        print(f"   回答: {native_result.answer[:150]}...")

        # Advanced RAG
        advanced_result = advanced_rag.query(question)
        print(f"\n🟢 Advanced RAG:")
        print(f"   用时: {advanced_result.response_time:.2f}s")
        print(f"   置信度: {advanced_result.confidence:.1%}")
        print(f"   来源: {advanced_result.source_count}个")
        print(f"   回答: {advanced_result.answer[:150]}...")

    print(f"\n{'='*60}")
    print("✅ 演示完成！")
    print("使用的正确模块:")
    print("  - langchain_text_splitters")
    print("  - langchain_community.document_loaders")
    print("  - langchain_classic.retrievers")
    print("  - langchain_openai")
    print("  - langchain_chroma")
    print(f"{'='*60}")


# ============================================
# 第十部分：脚本入口
# ============================================


if __name__ == "__main__":
    # 检查是否提供了命令行参数
    if len(sys.argv) > 1:
        if sys.argv[1] == "--demo":
            quick_demo()
        elif sys.argv[1] == "--interactive":
            interactive_mode()
        elif sys.argv[1] == "--test":
            # 运行测试
            asyncio.run(main_async())
        elif sys.argv[1] == "--help":
            print("""
            LangChain 1.2.x RAG 系统对比测试
            
            使用方法:
              python rag_system.py              # 主程序
              python rag_system.py --demo       # 快速演示
              python rag_system.py --interactive # 交互模式
              python rag_system.py --test       # 运行测试
              python rag_system.py --help       # 显示帮助
            
            环境变量:
              需要设置 DASHSCOPE_API_KEY
              示例: export DASHSCOPE_API_KEY=your-key-here
            """)
        else:
            print(f"❌ 未知参数: {sys.argv[1]}")
            print("使用 --help 查看帮助")
    else:
        # 默认运行主程序
        main()
