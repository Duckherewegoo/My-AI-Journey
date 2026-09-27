#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站智能视频推荐系统 (增强修复版)
功能：智能爬取B站视频、向量存储、语义搜索、个性化推荐
修复：Cookie解析、缩进语法、Gradio界面、缺失方法
"""

import os
import sys
import time
import json
import hashlib
import chromadb
import gradio as gr
import requests
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
import logging
import re
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from functools import lru_cache
import numpy as np
import pickle
from pathlib import Path
import warnings

from chromadb.config import Settings

# 忽略无关警告
warnings.filterwarnings("ignore")

# ====================== 全局配置 ======================
# 本地向量模型路径（首次运行会自动下载）
LOCAL_MODEL_PATH = "/run/media/dake/Software/Projects/Life/data/datasets/all-MiniLM-L6-v2"
# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_recommender.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====================== 数据模型定义 ======================


@dataclass
class VideoMetadata:
    """
    视频元数据 dataclass
    存储爬取的B站视频所有核心信息
    """
    bvid: str                          # B站视频唯一ID
    title: str                        # 视频标题
    author: str                       # UP主名称
    url: str                          # 视频链接
    play_count: int = 0               # 播放量
    duration: str = ""                # 视频时长
    publish_time: str = ""            # 发布时间
    tags: List[str] = field(default_factory=list)  # 视频标签
    description: str = ""             # 视频简介
    category: str = "未分类"           # 视频分类
    quality_score: float = 0.0        # 视频质量评分
    crawl_time: str = ""              # 爬取时间
    search_keyword: str = ""          # 爬取关键词

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于存储"""
        return asdict(self)

    def to_document(self) -> str:
        """
        转换为文本格式，用于生成向量
        拼接标题、作者、标签、简介、分类，作为语义检索的文本
        """
        parts = [
            f"标题: {self.title}",
            f"作者: {self.author}",
            f"标签: {', '.join(self.tags[:5])}",
            f"描述: {self.description[:100]}",
            f"分类: {self.category}"
        ]
        return " | ".join(parts)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VideoMetadata':
        """从字典反序列化为VideoMetadata对象"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

# ====================== Cookie管理器 ======================


class CookieManager:
    """
    B站Cookie管理工具类
    功能：解析Cookie字符串、格式化Cookie、提取关键Cookie
    """
    @staticmethod
    def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
        """
        解析任意格式的Cookie字符串为字典
        支持：换行分隔、分号分隔、制表符分隔等多种格式
        """
        cookies = {}
        if not cookie_str:
            return cookies

        logger.info(f"解析Cookie字符串: {cookie_str[:50]}...")

        # 去除固定前缀
        if cookie_str.startswith("Cookie: "):
            cookie_str = cookie_str[8:]

        # 按行分割解析
        lines = cookie_str.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 兼容多种分隔符
            if '\t' in line:
                parts = line.split('\t', 1)
            elif ' ' in line and '=' in line:
                parts = line.split(' ', 1)  # 修复：补充分割逻辑，消除空elif语法错误
            elif '=' in line:
                parts = line.split('=', 1)
            else:
                continue

            if len(parts) == 2:
                key, value = parts[0].strip(), parts[1].strip()
                # 去除值两端的引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                if key and value:
                    cookies[key] = value

        # 兜底：按分号分割解析
        if not cookies and '=' in cookie_str:
            for item in cookie_str.split(';'):
                item = item.strip()
                if '=' in item:
                    key, value = item.split('=', 1)
                    cookies[key.strip()] = value.strip()

        logger.info(f"成功解析 {len(cookies)} 个Cookie")
        return cookies

    @staticmethod
    def format_cookies(cookies: Dict[str, str]) -> str:
        """将Cookie字典格式化为HTTP请求头格式"""
        return '; '.join([f'{k}={v}' for k, v in cookies.items()])

    @staticmethod
    def get_essential_cookies(cookies: Dict[str, str]) -> Dict[str, str]:
        """提取B站必备的关键Cookie（登录/防风控必需）"""
        essential_keys = ['SESSDATA', 'bili_jct',
                          'DedeUserID', 'buvid3', 'buvid4']
        return {k: v for k, v in cookies.items() if k in essential_keys}

# ====================== 向量数据库管理器 ======================


class VideoDatabase:
    """
    基于ChromaDB的视频向量数据库
    功能：存储视频向量、元数据、语义搜索、数据管理
    """

    def __init__(self, persist_dir: str = "./video_database"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)

        try:
            # 初始化持久化Chroma客户端
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self._init_collections()
            logger.info(f"✅ 数据库初始化完成: {persist_dir}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def _init_collections(self):
        """初始化数据库集合（视频库+搜索历史）"""
        self.video_collection = self.client.get_or_create_collection(
            name="videos",
            metadata={"hnsw:space": "cosine"}  # 余弦相似度
        )
        self.history_collection = self.client.get_or_create_collection(
            name="search_history",
            metadata={"hnsw:space": "cosine"}
        )

    def get_video_count(self) -> int:
        """获取数据库中视频总数量"""
        try:
            return self.video_collection.count()
        except Exception as e:
            logger.warning(f"获取视频数量失败: {e}")
            return 0

    def is_empty(self) -> bool:
        """判断数据库是否为空"""
        return self.get_video_count() == 0

    def add_videos(self, videos: List[VideoMetadata], embeddings: List[List[float]]) -> int:
        """
        批量添加视频到数据库
        :param videos: 视频元数据列表
        :param embeddings: 视频向量列表
        :return: 成功添加的数量
        """
        if not videos or not embeddings:
            return 0

        try:
            ids, documents, metadatas = [], [], []
            for i, video in enumerate(videos):
                # 生成唯一ID
                video_id = f"{video.bvid}_{hashlib.md5(video.title.encode()).hexdigest()[:8]}_{i}"
                ids.append(video_id)
                documents.append(video.to_document())
                # 元数据序列化（列表转JSON）
                meta = video.to_dict()
                meta['tags'] = json.dumps(meta['tags'], ensure_ascii=False)
                metadatas.append(meta)

            # 分批插入（避免数据量过大报错）
            added_count = 0
            batch_size = 50
            for i in range(0, len(ids), batch_size):
                self.video_collection.add(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    embeddings=embeddings[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
                added_count += batch_size
            logger.info(f"✅ 成功添加 {added_count} 个视频")
            return added_count
        except Exception as e:
            logger.error(f"添加视频失败: {e}")
            return 0

    def search_videos(self, query_embedding: List[float], top_k: int = 5) -> List[Tuple[VideoMetadata, float]]:
        """
        语义搜索视频
        :param query_embedding: 搜索词向量
        :param top_k: 返回结果数量
        :return: 视频+相似度分数列表
        """
        if self.is_empty():
            return []

        try:
            actual_top_k = min(top_k, self.get_video_count())
            results = self.video_collection.query(
                query_embeddings=[query_embedding],
                n_results=actual_top_k,
                include=["metadatas", "distances"]
            )

            videos_with_scores = []
            for i, meta in enumerate(results["metadatas"][0]):
                try:
                    # 反序列化标签
                    meta['tags'] = json.loads(meta['tags']) if isinstance(
                        meta['tags'], str) else []
                    video = VideoMetadata.from_dict(meta)
                    similarity = max(0, 1.0 - results["distances"][0][i])
                    videos_with_scores.append((video, similarity))
                except Exception as e:
                    logger.warning(f"解析视频元数据失败: {e}")
            return videos_with_scores
        except Exception as e:
            logger.error(f"搜索视频失败: {e}")
            return []

    def get_sample_videos(self, limit: int = 5) -> List[VideoMetadata]:
        """获取数据库中的示例视频"""
        if self.is_empty():
            return []
        try:
            all_data = self.video_collection.get()
            videos = []
            for meta in all_data.get("metadatas", [])[:limit]:
                try:
                    meta['tags'] = json.loads(meta['tags']) if isinstance(
                        meta['tags'], str) else []
                    videos.append(VideoMetadata.from_dict(meta))
                except:
                    continue
            return videos
        except Exception as e:
            logger.warning(f"获取示例视频失败: {e}")
            return []

# ====================== B站视频爬虫 ======================


class BilibiliCrawler:
    """
    B站视频爬虫（增强版）
    功能：Cookie验证、关键词爬取、视频解析、风控处理
    """

    def __init__(self, cookie_str: str = None):
        # 请求头（模拟浏览器，防反爬）

        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Referer": "https://search.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://search.bilibili.com",
        }

        # 初始化Cookie
        self.cookies = CookieManager.parse_cookie_string(
            cookie_str) if cookie_str else {}
        if self.cookies:
            self.headers['Cookie'] = CookieManager.format_cookies(self.cookies)

        # 创建会话+自动重试
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        adapter = requests.adapters.HTTPAdapter(max_retries=3)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        logger.info("✅ B站爬虫初始化完成")

    def test_cookie(self) -> Tuple[bool, str]:
        """测试Cookie是否有效（B站登录校验）"""
        try:
            url = "https://api.bilibili.com/x/web-interface/nav"
            response = self.session.get(url, timeout=10)
            if response.status_code == 412:
                return False, "❌ 触发风控，请检查Cookie"
            if response.status_code != 200:
                return False, f"❌ 请求失败：HTTP {response.status_code}"

            data = response.json()
            if data.get("code") != 0:
                return False, f"❌ Cookie无效：{data.get('message')}"

            # 校验必备Cookie
            essential = CookieManager.get_essential_cookies(self.cookies)
            missing = [k for k in ['SESSDATA', 'bili_jct']
                       if k not in essential]
            if missing:
                return False, f"❌ 缺少关键Cookie：{', '.join(missing)}"

            uname = data.get("data", {}).get("uname", "未知用户")
            return True, f"✅ Cookie有效，用户：{uname}"
        except Exception as e:
            return False, f"❌ 测试失败：{str(e)}"

    def crawl_videos(self, keyword: str, max_results: int = 20) -> Tuple[List[VideoMetadata], str, bool]:
        """
        按关键词爬取B站视频
        :param keyword: 搜索关键词
        :param max_results: 最大爬取数量
        :return: 视频列表、错误信息、是否触发风控
        """
        videos, page, error_msg, fengkong = [], 1, "", False
        logger.info(f"🔍 开始爬取关键词：{keyword}")

        while len(videos) < max_results and page <= 5:
            try:
                url = "https://api.bilibili.com/x/web-interface/search/type"
                params = {
                    "keyword": keyword,
                    "search_type": "video",
                    "page": page,
                    "page_size": 20,
                    "order": "totalrank",
                    # 新增B站必填参数，修复空结果
                    "platform": "web",
                    "web_location": 1430654,
                }

                response = self.session.get(url, params=params, timeout=15)

                if response.status_code == 412:
                    fengkong = True
                    error_msg = "触发B站风控"
                    break

                data = response.json()
                # 新增这一行，打印完整响应（必加，定位问题）
                logger.info(
                    f"API完整响应: {json.dumps(data, ensure_ascii=False, indent=2)}")

                if data.get("code") != 0:
                    error_msg = f"API错误：{data.get('message')}"
                    break

                video_list = data.get("data", {}).get("result", [])
                if not video_list:
                    error_msg = "无更多视频"
                    break

                # 解析视频
                for item in video_list[:max_results-len(videos)]:
                    video = self._parse_video_item(item, keyword)
                    if video:
                        videos.append(video)

                page += 1
                time.sleep(1)  # 礼貌延迟，防风控
            except Exception as e:
                error_msg = f"爬取异常：{str(e)}"
                break

        logger.info(f"📥 爬取完成：{len(videos)} 个视频")
        return videos, error_msg, fengkong

    def _parse_video_item(self, item: Dict[str, Any], keyword: str) -> Optional[VideoMetadata]:
        """解析单个视频API数据为元数据对象"""
        try:
            bvid = item.get("bvid")
            if not bvid:
                return None

            # 清理标题（去除HTML标签）
            title = re.sub(r'<[^>]+>', '', item.get("title", "")).strip()
            play_count = int(item.get("play", 0))

            # ============== 修复核心BUG ==============
            # API返回的duration是字符串(如1301:52)，不是秒数，直接使用
            duration_str = item.get("duration", "未知")
            # 无需转int，直接赋值
            # ========================================

            # 质量评分（修复：移除依赖秒数的判断，避免报错）
            quality = 0.0
            if play_count > 10000:
                quality += 0.3

            # 标签处理
            tags = [t.strip() for t in item.get("tag", "").split(",")
                    ][:5] if item.get("tag") else []
            # 分类猜测
            category = self._guess_category(title, item.get("tag", ""))

            return VideoMetadata(
                bvid=bvid, title=title, author=item.get("author", "未知UP主"),
                url=f"https://www.bilibili.com/video/{bvid}", play_count=play_count,
                duration=duration_str,  # 直接用API返回的时长字符串
                publish_time=datetime.fromtimestamp(int(item.get("pubdate", 0))).strftime(
                    "%Y-%m-%d %H:%M") if item.get("pubdate") else "未知",
                tags=tags, description=item.get("description", "")[:100],
                category=category, quality_score=min(quality, 1.0),
                crawl_time=datetime.now().isoformat(), search_keyword=keyword
            )
        except Exception as e:
            # 打印错误，方便排查
            logger.error(f"解析视频失败: {e} | item: {item.get('bvid')}")
            return None

    def _format_duration(self, seconds: int) -> str:
        """秒数转换为时分秒格式"""
        if seconds <= 0:
            return "未知"
        h, m, s = seconds//3600, (seconds % 3600)//60, seconds % 60
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def _guess_category(self, title: str, tags: str) -> str:
        """根据标题/标签智能分类视频"""
        title, tags = title.lower(), tags.lower() if tags else ""
        categories = {
            "教程": ["教程", "教学", "入门", "学习"], "科技": ["科技", "数码", "编程"],
            "游戏": ["游戏", "电竞", "原神"], "生活": ["vlog", "日常", "旅行"],
            "音乐": ["音乐", "歌曲"], "影视": ["电影", "动漫"], "知识": ["科普", "历史"], "搞笑": ["搞笑", "沙雕"]
        }
        for cat, keys in categories.items():
            if any(k in title or k in tags for k in keys):
                return cat
        return "其他"

# ====================== 向量模型管理器 ======================


class EmbeddingManager:
    """
    文本向量编码管理器
    功能：加载模型、文本转向量、批量编码、缓存优化
    """

    def __init__(self, model_path: str = LOCAL_MODEL_PATH):
        self.model = None
        self.dimension = 384
        try:
            logger.info(f"加载向量模型：{model_path}")
            # 优先加载本地模型，无则自动下载
            self.model = SentenceTransformer(model_path) if os.path.exists(
                model_path) else SentenceTransformer("all-MiniLM-L6-v2")
            self.model.save(model_path)  # 保存到本地
            self.dimension = self.model.get_sentence_embedding_dimension()
            logger.info(f"✅ 模型加载成功，向量维度：{self.dimension}")
        except Exception as e:
            logger.error(f"模型加载失败：{e}")
            raise

    @lru_cache(maxsize=1000)
    def encode(self, text: str) -> List[float]:
        """单文本编码（带缓存，提升速度）"""
        return self.model.encode(text).tolist() if self.model else [0.0]*self.dimension

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """批量文本编码（修复原代码缺失的核心方法）"""
        return self.model.encode(texts).tolist() if self.model else [[0.0]*self.dimension for _ in texts]

# ====================== 推荐引擎核心 ======================


class VideoRecommender:
    """
    视频推荐引擎（核心业务类）
    整合：爬虫、向量模型、数据库，提供爬取/搜索/统计功能
    """

    def __init__(self, model_path: str = LOCAL_MODEL_PATH):
        self.embedder = EmbeddingManager(model_path)
        self.database = VideoDatabase()
        self.crawler = None
        self.cookie_valid = False
        self.ai_service = self._init_ai_service()
        logger.info("🚀 推荐引擎初始化完成")

    def _init_ai_service(self):
        """初始化千问AI服务（可选）"""
        try:
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                return None
            return OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        except:
            return None

    def set_cookie(self, cookie_str: str) -> Tuple[bool, str]:
        """设置并校验B站Cookie"""
        try:
            self.crawler = BilibiliCrawler(cookie_str)
            self.cookie_valid, msg = self.crawler.test_cookie()
            return self.cookie_valid, msg
        except Exception as e:
            return False, f"设置失败：{str(e)}"

    def crawl_videos(self, keyword: str, max_count: int = 20) -> Tuple[str, List[VideoMetadata]]:
        """爬取视频并入库"""
        if not self.cookie_valid or not self.crawler:
            return "❌ 请先设置有效Cookie", []

        start = time.time()
        videos, err, fengkong = self.crawler.crawl_videos(keyword, max_count)
        if fengkong:
            return f"❌ {err}，请更换Cookie", []
        if not videos:
            return f"❌ 爬取失败：{err}", []

        # 生成向量并入库
        embeddings = self.embedder.encode_batch(
            [v.to_document() for v in videos])
        added = self.database.add_videos(videos, embeddings)
        cost = time.time() - start

        return (
            f"✅ 爬取完成\n关键词：{keyword}\n获取：{len(videos)}个\n入库：{added}个\n耗时：{cost:.2f}s",
            videos
        )

    def search_videos(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """语义搜索视频"""
        if self.database.is_empty():
            return {"error": "数据库为空，请先爬取", "results": []}
        start = time.time()
        embed = self.embedder.encode(query)
        results = self.database.search_videos(embed, top_k)
        return {
            "query": query, "results": [{"video": v, "score": s} for v, s in results],
            "search_time": time.time()-start, "total_found": len(results)
        }

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统状态统计"""
        return {
            "video_count": self.database.get_video_count(),
            "sample_videos": self.database.get_sample_videos(3),
            "ai_available": self.ai_service is not None,
            "cookie_valid": self.cookie_valid,
            "model_dimension": self.embedder.dimension
        }

# ====================== Gradio Web界面 ======================


class VideoApp:
    """Gradio Web界面封装类"""

    def __init__(self, recommender: VideoRecommender):
        self.recommender = recommender

    def create_interface(self) -> gr.Blocks:
        """创建完整Web界面（修复所有缩进/嵌套错误）"""
        with gr.Blocks(title="B站智能视频推荐系统", theme="soft") as app:
            # 页面标题
            gr.Markdown("# 🎬 B站智能视频推荐系统")
            gr.Markdown("智能爬取、语义搜索、个性化推荐B站视频")

            # ========== Cookie设置区域 ==========
            with gr.Accordion("🔐 B站Cookie设置 (必填，避免风控)", open=True):
                gr.Markdown("""
                **获取Cookie教程**：
                1. 登录B站网页版 → 按F12 → Network → 刷新页面
                2. 复制任意请求的 `Request Headers` 中的 `Cookie` 字段
                """)
                with gr.Row():
                    cookie_input = gr.Textbox(
                        label="粘贴Cookie", placeholder="完整Cookie字符串...", lines=3)
                    test_cookie_btn = gr.Button("🔍 测试Cookie", size="sm")
                cookie_status = gr.Textbox(
                    label="Cookie状态", value="未设置Cookie", interactive=False)

            # ========== 主功能标签页 ==========
            with gr.Tabs():
                # 标签1：智能搜索
                with gr.Tab("🔍 智能搜索"):
                    with gr.Row():
                        # 左侧控制面板
                        with gr.Column(scale=1):
                            with gr.Group():
                                gr.Markdown("### 搜索设置")
                                search_input = gr.Textbox(
                                    label="搜索关键词", placeholder="Python教程/科技评测...", lines=2)
                                top_k_slider = gr.Slider(
                                    label="结果数量", minimum=1, maximum=10, value=5)
                            search_btn = gr.Button(
                                "开始搜索", variant="primary", size="lg")
                            with gr.Group():
                                db_status = gr.Textbox(
                                    label="状态", interactive=False)
                        # 右侧结果面板
                        with gr.Column(scale=2):
                            search_output = gr.Markdown(
                                label="搜索结果", value="等待搜索...")
                            results_table = gr.Dataframe(
                                label="视频列表", wrap=True)
                            with gr.Accordion("🔗 视频链接", open=False):
                                video_links = gr.Textbox(label="链接", lines=3)

                # 标签2：手动爬取
                with gr.Tab("📥 手动爬取"):
                    with gr.Row():
                        with gr.Column(scale=1):
                            gr.Markdown("### 爬取视频")
                            crawl_keyword = gr.Textbox(
                                label="关键词", placeholder="输入爬取关键词")
                            crawl_count = gr.Slider(
                                label="爬取数量", minimum=5, maximum=30, value=10)
                            crawl_btn = gr.Button(
                                "🌐 开始爬取", variant="secondary")
                        with gr.Column(scale=2):
                            crawl_output = gr.Markdown(
                                label="爬取结果", value="等待爬取...")

                # 标签3：系统统计
                with gr.Tab("📊 系统统计"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### 系统状态")
                            stats_output = gr.Markdown()
                            refresh_stats_btn = gr.Button("🔄 刷新统计")
                        with gr.Column():
                            gr.Markdown("### 样本视频")
                            sample_table = gr.Dataframe(wrap=True)

                # 标签4：使用说明
                with gr.Tab("❓ 使用说明"):
                    gr.Markdown("""
                    ### 使用流程
                    1. **设置Cookie** → 测试有效
                    2. **爬取视频** → 填充数据库
                    3. **智能搜索** → 语义匹配视频

                    ### 常见问题
                    - 触发风控：更换Cookie/降低爬取频率
                    - 搜索无结果：先爬取视频
                    - Cookie无效：重新登录B站复制
                    """)

            # ====================== 界面事件绑定 ======================
            # 测试Cookie
            test_cookie_btn.click(
                fn=self.handle_set_cookie,
                inputs=cookie_input,
                outputs=cookie_status
            )
            # 搜索视频
            search_btn.click(
                fn=self.handle_search,
                inputs=[search_input, top_k_slider],
                outputs=[search_output, results_table,
                         video_links, sample_table]
            )
            # 爬取视频
            crawl_btn.click(
                fn=self.handle_crawl,
                inputs=[crawl_keyword, crawl_count],
                outputs=[crawl_output, sample_table]
            )
            # 刷新统计
            refresh_stats_btn.click(
                fn=self.get_system_stats,
                outputs=stats_output
            )
            # 页面加载初始化
            app.load(self.get_db_status, outputs=[db_status, sample_table])
            app.load(self.get_system_stats, outputs=stats_output)

        return app

    # ====================== 界面交互函数 ======================
    def handle_set_cookie(self, cookie_str):
        """处理Cookie设置与校验"""
        if not cookie_str:
            return "❌ 请输入Cookie"
        success, msg = self.recommender.set_cookie(cookie_str)
        return f"✅ {msg}" if success else f"❌ {msg}"

    def handle_search(self, query, top_k):
        """处理搜索请求，渲染结果"""
        if not query:
            return "请输入搜索内容", pd.DataFrame(), "", pd.DataFrame()
        res = self.recommender.search_videos(query, int(top_k))
        if "error" in res:
            return f"❌ {res['error']}", pd.DataFrame(), "", pd.DataFrame()

        # 构建结果文本
        text = f"## 搜索结果\n查询：{res['query']}\n找到：{res['total_found']}个\n耗时：{res['search_time']:.2f}s"
        # 构建表格数据
        table, links = [], []
        for i, item in enumerate(res["results"], 1):
            v, s = item["video"], item["score"]
            table.append([i, v.title[:40], v.author,
                         f"{s*100:.1f}%", f"{v.play_count:,}", v.duration, v.category])
            links.append(f"{i}. {v.url}")
        df = pd.DataFrame(table, columns=[
                          "排名", "标题", "UP主", "匹配度", "播放量", "时长", "分类"]) if table else pd.DataFrame()
        return text, df, "\n".join(links), self.get_sample_videos()

    def handle_crawl(self, keyword, count):
        """处理爬取请求"""
        if not keyword:
            return "请输入关键词", pd.DataFrame()
        result, _ = self.recommender.crawl_videos(keyword, int(count))
        return result, self.get_sample_videos()

    def get_system_stats(self):
        """获取系统统计信息"""
        s = self.recommender.get_system_stats()
        return f"""## 系统统计
视频总数：{s['video_count']} 个
Cookie状态：{'✅ 有效' if s['cookie_valid'] else '❌ 无效'}
AI服务：{'✅ 可用' if s['ai_available'] else '❌ 不可用'}
向量维度：{s['model_dimension']}"""

    def get_db_status(self):
        """获取数据库状态"""
        cnt = self.recommender.get_system_stats()['video_count']
        return f"✅ 视频库：{cnt} 个" if cnt else "⚠️ 数据库为空，请先爬取", self.get_sample_videos()

    def get_sample_videos(self):
        """获取样本视频表格"""
        samples = self.recommender.get_system_stats()['sample_videos']
        data = [[v.title[:30], v.author,
                 f"{v.play_count:,}", v.category] for v in samples]
        return pd.DataFrame(data, columns=["标题", "UP主", "播放量", "分类"])

# ====================== 主程序入口 ======================


def main():
    """程序启动入口"""
    print("="*60)
    print("🚀 B站智能视频推荐系统 (修复版)")
    print("="*60)

    try:
        # 初始化核心引擎
        recommender = VideoRecommender(LOCAL_MODEL_PATH)
        # 创建Web界面
        app = VideoApp(recommender)
        demo = app.create_interface()

        print("\n✅ 系统初始化完成！")
        print(f"📊 视频库现有：{recommender.database.get_video_count()} 个")
        print("🌐 访问地址：http://localhost:7860")
        print("⚠️ 首次使用必须先设置B站Cookie！")

        # 启动Web服务
        demo.launch(server_name="0.0.0.0", server_port=7860, share=False)

    except KeyboardInterrupt:
        print("\n👋 程序已退出")
    except Exception as e:
        print(f"\n❌ 启动失败：{e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
    main()
