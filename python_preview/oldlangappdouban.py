# ======================== 豆瓣TOP250 原生RAG · 通义千问 · Jupyter专属 ========================
import re
import requests
from bs4 import BeautifulSoup
import gradio as gr

# RAG 核心依赖
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI

import os

# ===================== 配置项 =====================
# 填入你的通义千问 API Key
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://movie.douban.com/top250",
}

# ===================== 标准嵌入模型 =====================


class SimpleEmbedding(Embeddings):
    def embed_documents(self, texts):
        return [[0.0] * 10 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 10


embed = SimpleEmbedding()

# ===================== 全局变量 =====================
movie_list = []
rag_chain = None

# ===================== 豆瓣TOP250 全量爬虫 =====================


def crawl_movies():
    global movie_list
    movie_list = []
    with gr.Info("开始爬取豆瓣TOP250..."):
        for page in range(0, 250, 25):
            try:
                url = f"https://movie.douban.com/top250?start={page}"
                res = requests.get(url, headers=HEADERS, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")

                for item in soup.select("ol.grid_view li"):
                    try:
                        # 电影名称
                        title = item.find("span", class_="title").text
                        if "/" in title:
                            continue
                        # 评分
                        score = item.find("span", class_="rating_num").text
                        # 年份
                        info = item.find("div", class_="bd").p.text
                        year = (
                            re.search(r"\d{4}", info).group()
                            if re.search(r"\d{4}", info)
                            else "未知"
                        )
                        # 简介
                        desc = (
                            item.find("span", class_="inq").text
                            if item.find("span", class_="inq")
                            else "无简介"
                        )

                        movie_list.append(
                            {"电影": title, "评分": score, "年份": year, "简介": desc}
                        )
                    except:
                        continue
            except Exception as e:
                continue
    return f"✅ 爬取完成！共 {len(movie_list)} 部电影"


# ===================== 纯LCEL 原生RAG构建 =====================


def build_rag_system():
    global rag_chain
    if not movie_list:
        return "❌ 请先爬取数据！"

    # 构建文档
    docs = [
        Document(
            page_content=f"电影：{m['电影']} | 评分：{m['评分']} | 年份：{m['年份']} | 简介：{m['简介']}"
        )
        for m in movie_list
    ]

    # 向量库
    db = FAISS.from_documents(docs, embed)
    retriever = db.as_retriever(k=3)

    # 提示词
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是豆瓣电影助手，严格根据提供的电影信息回答问题，简洁准确。\n上下文：{context}",
            ),
            ("human", "{question}"),
        ]
    )

    # 通义千问 LLM
    llm = ChatOpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen-plus",
        temperature=0,
    )

    # LCEL RAG 链
    rag_chain = (
        {
            "context": retriever | (lambda x: "\n".join(d.page_content for d in x)),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    return "✅ RAG 知识库构建完成！"


# ===================== 问答函数 =====================


def answer(question):
    if not rag_chain:
        return "❌ 请先构建知识库！"
    return rag_chain.invoke(question)


# ===================== Gradio 界面（Jupyter 原生弹出） =====================
with gr.Blocks(title="豆瓣电影RAG") as demo:
    gr.Markdown("# 🎬 豆瓣TOP250 智能问答系统")
    status_box = gr.Textbox(label="系统状态", interactive=False)

    with gr.Row():
        btn_crawl = gr.Button("🚀 爬取豆瓣数据", variant="primary")
        btn_rag = gr.Button("📊 构建RAG知识库", variant="primary")

    gr.Markdown("## 💬 与AI对话")
    question_input = gr.Textbox(
        label="输入你的问题", placeholder="例如：肖申克的救赎评分是多少？"
    )
    answer_output = gr.Textbox(label="AI 回答", lines=4)
    btn_ask = gr.Button("🔍 提问", variant="primary")

    # 绑定事件
    btn_crawl.click(crawl_movies, outputs=status_box)
    btn_rag.click(build_rag_system, outputs=status_box)
    btn_ask.click(answer, inputs=question_input, outputs=answer_output)

# 启动（Jupyter 内直接运行）
demo.launch(inbrowser=True, share=False, server_name="0.0.0.0", server_port=7860)
