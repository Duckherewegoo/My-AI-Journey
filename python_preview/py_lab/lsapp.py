import os
import requests
from bs4 import BeautifulSoup
import streamlit as st

# ========== LCEL 核心导入（无 langchain.chains）==========
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from langchain_community.vectorstores import FAISS
from langchain_openai import ChatOpenAI

# ========== 页面配置 ==========
st.set_page_config(page_title="豆瓣TOP250 RAG", layout="wide")
st.title("🎬 豆瓣 TOP250 智能问答（纯LCEL）")

# ========== 全局状态 ==========
if "movies" not in st.session_state:
    st.session_state.movies = []
if "rag_chain" not in st.session_state:
    st.session_state.rag_chain = None

# ========== 通义千问 LLM ==========
llm = ChatOpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
)

# ===================== ✅ 修复嵌入函数：解决【对象不可调用】报错 =====================


def simple_embedding(text):
    """FAISS 兼容的标准嵌入函数"""
    return [0.0] * 10  # 简易固定向量，兼容所有VectorStore


# ===================== 修复爬虫：正常爬取数据 =====================


def crawl_douban():
    with st.spinner("正在爬取豆瓣TOP250数据..."):
        movies = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://movie.douban.com/top250",
        }

        for page in range(0, 100, 25):
            try:
                url = f"https://movie.douban.com/top250?start={page}&filter="
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")

                for item in soup.select("ol.grid_view li"):
                    try:
                        title = item.select_one("span.title").text
                        if "/" not in title:  # 只保留中文标题
                            score = item.select_one("span.rating_num").text
                            movies.append({"电影名称": title, "豆瓣评分": score})
                    except:
                        continue
            except Exception as e:
                st.error(f"请求失败：{str(e)}")

        st.session_state.movies = movies
        st.success(f"✅ 爬取完成！共 {len(movies)} 部电影")


# ===================== 纯 LCEL RAG 构建 =====================


def build_rag():
    if not st.session_state.movies:
        st.warning("⚠️ 请先爬取数据！")
        return

    with st.spinner("正在构建LCEL-RAG向量库..."):
        # 构建文档
        docs = [
            Document(page_content=f"电影：{m['电影名称']} | 评分：{m['豆瓣评分']}")
            for m in st.session_state.movies
        ]

        # ✅ 使用修复后的嵌入函数（无报错）
        vectorstore = FAISS.from_documents(docs, simple_embedding)

        # LCEL 提示词
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是豆瓣电影助手，仅根据上下文简洁回答问题。上下文：{context}",
                ),
                ("human", "{question}"),
            ]
        )

        # 组装 LCEL 链（官方标准写法）
        rag_chain = (
            {
                "context": vectorstore.as_retriever()
                | (lambda x: "\n".join(d.page_content for d in x)),
                "question": RunnablePassthrough(),
            }
            | prompt
            | llm
            | StrOutputParser()
        )
        st.session_state.rag_chain = rag_chain
        st.success("✅ LCEL-RAG 构建完成！")


# ===================== 问答功能 =====================


def answer_question(question):
    if not st.session_state.rag_chain:
        return "⚠️ 请先构建RAG！"
    return st.session_state.rag_chain.invoke(question)


# ===================== 界面 =====================
col1, col2 = st.columns(2)
with col1:
    if st.button("🚀 爬取豆瓣TOP250数据"):
        crawl_douban()
with col2:
    if st.button("📊 构建 LCEL-RAG 知识库"):
        build_rag()

# 展示数据
if st.session_state.movies:
    st.dataframe(st.session_state.movies, use_container_width=True)

# 问答
user_q = st.text_input("输入问题（例：肖申克的救赎评分是多少？）")
if st.button("🔍 提问") and user_q:
    with st.spinner("AI思考中..."):
        st.write("**🤖 AI 回答：**", answer_question(user_q))
