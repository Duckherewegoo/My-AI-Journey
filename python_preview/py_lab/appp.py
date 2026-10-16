import os
import gradio as gr
from typing import List, Tuple
from openai import OpenAI
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
import tempfile
import uuid

# 加载环境变量
load_dotenv()

# 初始化组件
st = os.path.join("/home/dake/Documents/Project/Life/data/paraphrase")


class NativeRAGSystem:
    def __init__(self):
        # 初始化LLM客户端
        self.client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.model_name = "qwen-plus"

        # 初始化向量数据库
        self.chroma_client = chromadb.Client(
            Settings(persist_directory="./chroma_db", anonymized_telemetry=False)
        )

        # 初始化embedding模型（使用本地模型，避免额外API调用）
        self.embedding_model = st

        # 初始化文本分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", "、", ""],
        )

        # 创建/获取集合
        self.collection_name = "rag_documents"
        try:
            self.collection = self.chroma_client.get_collection(
                name=self.collection_name
            )
        except:
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )

    def embed_text(self, texts: List[str]) -> List[List[float]]:
        """本地生成embedding"""
        embeddings = self.embedding_model.encode(texts)
        return embeddings.tolist()

    def process_document(self, file) -> Tuple[str, int]:
        """处理上传的文档"""
        if file is None:
            return "请先上传文件", 0

        try:
            # 保存上传的文件
            temp_path = f"./data/{uuid.uuid4().hex}{os.path.splitext(file.name)[1]}"
            os.makedirs("./data", exist_ok=True)

            with open(temp_path, "wb") as f:
                f.write(file.read())

            # 根据文件类型加载
            if file.name.endswith(".pdf"):
                from langchain_community.document_loaders import PyPDFLoader

                loader = PyPDFLoader(temp_path)
            elif file.name.endswith(".txt"):
                from langchain_community.document_loaders import TextLoader

                loader = TextLoader(temp_path, encoding="utf-8")
            else:
                return f"不支持的文件格式: {os.path.splitext(file.name)[1]}", 0

            documents = loader.load()

            # 分割文本
            chunks = self.text_splitter.split_documents(documents)

            if not chunks:
                return "文档内容为空或无法解析", 0

            # 准备数据
            texts = [chunk.page_content for chunk in chunks]
            metadatas = [
                {"source": file.name, "chunk_index": i} for i in range(len(chunks))
            ]
            ids = [f"{file.name}_{i}" for i in range(len(chunks))]

            # 生成embedding
            embeddings = self.embed_text(texts)

            # 存储到向量数据库
            self.collection.add(
                embeddings=embeddings, documents=texts, metadatas=metadatas, ids=ids
            )

            # 清理临时文件
            os.remove(temp_path)

            return f"✅ 文档 '{file.name}' 处理成功！\n分割成 {len(chunks)} 个文本块，已存入知识库。", len(
                chunks
            )

        except Exception as e:
            return f"❌ 处理文档时出错: {str(e)}", 0

    def search_similar(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """检索相似文档"""
        if not query or query.strip() == "":
            return []

        # 生成query的embedding
        query_embedding = self.embed_text([query])[0]

        # 搜索
        results = self.collection.query(query_embeddings=[query_embedding], n_results=k)

        # 格式化结果
        retrieved_docs = []
        if results["documents"] and results["documents"][0]:
            for doc, metadata, distance in zip(
                results["documents"][0],
                results["metadatas"][0] if results["metadatas"] else [],
                results["distances"][0] if results["distances"] else [],
            ):
                source = metadata.get("source", "未知") if metadata else "未知"
                retrieved_docs.append(
                    (doc, source, 1.0 - distance if distance else 0.0)
                )

        return retrieved_docs

    def generate_answer(self, query: str, use_rag: bool = True) -> str:
        """生成回答"""
        if not query or query.strip() == "":
            return "请输入问题"

        try:
            context = ""
            if use_rag:
                # 检索相关文档
                retrieved_docs = self.search_similar(query, k=3)

                if retrieved_docs:
                    context = "参考知识库中的相关信息：\n\n"
                    for i, (doc, source, score) in enumerate(retrieved_docs, 1):
                        context += (
                            f"[信息{i}，来源：{source}，相关性：{score:.2f}]\n{doc}\n\n"
                        )
                else:
                    context = "（知识库中暂无相关信息）\n\n"

            # 构建消息
            system_prompt = """你是一个专业的AI助手，基于用户的问题和提供的参考信息进行回答。
            如果参考信息中有相关答案，请基于这些信息给出准确的回答，并注明信息来源。
            如果参考信息中没有相关答案，请基于你自己的知识进行回答，但要说明这是基于通用知识。"""

            user_prompt = f"{context}用户问题：{query}\n\n请给出专业、准确的回答："

            # 调用LLM
            completion = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            answer = completion.choices[0].message.content

            # 在答案末尾添加参考信息
            if use_rag and retrieved_docs:
                answer += "\n\n---\n**📚 参考来源：**\n"
                for i, (_, source, score) in enumerate(retrieved_docs, 1):
                    answer += f"{i}. {source} (相关性: {score:.2f})\n"

            return answer

        except Exception as e:
            return f"❌ 生成回答时出错: {str(e)}"

    def clear_knowledge_base(self) -> str:
        """清空知识库"""
        try:
            self.chroma_client.delete_collection(name=self.collection_name)
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name, metadata={"hnsw:space": "cosine"}
            )
            return "✅ 知识库已清空！"
        except Exception as e:
            return f"❌ 清空知识库时出错: {str(e)}"

    def get_stats(self) -> str:
        """获取知识库统计信息"""
        try:
            count = self.collection.count()
            return f"📊 知识库统计：\n当前文档块数量：{count} 个"
        except:
            return "知识库为空或未初始化"


# 初始化系统
rag_system = NativeRAGSystem()

# 创建Gradio界面


def create_interface():
    with gr.Blocks(title="本地RAG系统", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # 🤖 本地RAG系统
        基于DashScope API和Chroma向量数据库构建的检索增强生成系统
        """)

        with gr.Tab("📁 文档上传"):
            with gr.Row():
                with gr.Column(scale=2):
                    file_input = gr.File(label="上传文档", file_types=[".txt", ".pdf"])
                    upload_btn = gr.Button("处理并存入知识库", variant="primary")
                    clear_btn = gr.Button("清空知识库", variant="stop")

                with gr.Column(scale=3):
                    output_status = gr.Textbox(
                        label="处理状态", lines=4, interactive=False
                    )
                    stats_display = gr.Textbox(
                        label="知识库统计", lines=2, interactive=False
                    )

            upload_btn.click(
                fn=rag_system.process_document,
                inputs=[file_input],
                outputs=[output_status, stats_display],
            )

            clear_btn.click(
                fn=rag_system.clear_knowledge_base, inputs=[], outputs=[stats_display]
            )

        with gr.Tab("💬 问答对话"):
            with gr.Row():
                with gr.Column(scale=2):
                    query_input = gr.Textbox(
                        label="输入问题", lines=3, placeholder="请输入您的问题..."
                    )

                    with gr.Row():
                        use_rag_checkbox = gr.Checkbox(
                            label="使用RAG检索增强", value=True
                        )
                        submit_btn = gr.Button("获取答案", variant="primary", size="lg")

                    with gr.Accordion("🔍 查看检索结果", open=False):
                        retrieval_results = gr.Dataframe(
                            headers=["内容", "来源", "相关性"],
                            datatype=["str", "str", "number"],
                            col_count=(3, "fixed"),
                            interactive=False,
                        )

                with gr.Column(scale=3):
                    answer_output = gr.Textbox(
                        label="AI回答", lines=12, interactive=False
                    )

            # 检索相似内容
            query_input.change(
                fn=lambda query: rag_system.search_similar(query, k=3),
                inputs=[query_input],
                outputs=[retrieval_results],
            )

            # 生成回答
            submit_btn.click(
                fn=rag_system.generate_answer,
                inputs=[query_input, use_rag_checkbox],
                outputs=[answer_output],
            )

        with gr.Tab("📊 系统信息"):
            gr.Markdown("""
            ### 系统配置
            - **LLM模型**: qwen-plus (通过DashScope API)
            - **向量数据库**: Chroma (本地持久化)
            - **Embedding模型**: paraphrase-multilingual-MiniLM-L12-v2
            - **文本分割**: 递归字符分割，块大小500，重叠50
            
            ### 使用方法
            1. 在"文档上传"标签页上传TXT或PDF文件
            2. 系统会自动处理文档并存入向量数据库
            3. 在"问答对话"标签页提问
            4. 勾选"使用RAG检索增强"可结合知识库回答
            
            ### 环境变量
            需要设置 `DASHSCOPE_API_KEY` 环境变量
            """)

            api_key_status = gr.Textbox(
                label="API Key状态",
                value=f"已设置: {os.getenv('DASHSCOPE_API_KEY', '未设置')[:10]}...",
                interactive=False,
            )

        # 初始化显示统计
        demo.load(fn=rag_system.get_stats, inputs=[], outputs=[stats_display])

    return demo


# 主程序
if __name__ == "__main__":
    # 创建数据目录
    os.makedirs("./data", exist_ok=True)
    os.makedirs("./chroma_db", exist_ok=True)

    # 检查API密钥
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("⚠️  警告: 未找到DASHSCOPE_API_KEY环境变量")
        print("请创建.env文件或在启动前设置环境变量")
        print("示例: export DASHSCOPE_API_KEY=sk-xxx")

    # 启动界面
    demo = create_interface()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False, debug=True)
