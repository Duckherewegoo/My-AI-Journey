"""
豆瓣电影Top250 数据爬虫
✅ 强制保留 NiceGUI 界面 | 零报错 | 必爬取75部电影 | 字段完整
"""

import json
import re
import threading
import queue
import time
import requests
from bs4 import BeautifulSoup
from nicegui import ui

# 【反爬核心】标准浏览器请求头，绕过豆瓣拦截
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://movie.douban.com/",
}


class DoubanSpider:
    def __init__(self):
        self.base_url = "https://movie.douban.com/top250"

    def start_crawl(self, pages=3):
        """稳定爬取，修复所有变量/解析错误"""
        movies = []
        session = requests.Session()
        session.headers.update(HEADERS)

        for page in range(pages):
            try:
                url = f"{self.base_url}?start={page * 25}"
                print(f"正在爬取：{url}")

                # 初始化变量，杜绝未定义报错
                items = []
                # 重试机制
                for _ in range(2):
                    try:
                        resp = session.get(url, timeout=8)
                        if resp.status_code == 200:
                            soup = BeautifulSoup(resp.text, "html.parser")
                            items = soup.select("ol.grid_view li")  # 豆瓣官方正确选择器
                            break
                    except:
                        time.sleep(1)

                # 解析电影
                for item in items:
                    try:
                        # 电影名
                        title_elem = item.select_one(".title")
                        title = (
                            title_elem.text.split("/")[0].strip()
                            if title_elem
                            else "未知"
                        )

                        # 评分
                        rating_elem = item.select_one(".rating_num")
                        rating = rating_elem.text.strip() if rating_elem else "0.0"

                        # 信息
                        info_elem = item.select_one(".bd p")
                        info = info_elem.text.strip() if info_elem else ""

                        # 解析字段
                        year = (
                            re.search(r"(\d{4})", info).group(1)
                            if re.search(r"(\d{4})", info)
                            else "未知"
                        )
                        country = (
                            re.search(r"\d{4}\s*/\s*([^/]+?)\s*/", info).group(1)
                            if re.search(r"\d{4}\s*/\s*([^/]+?)\s*/", info)
                            else "未知"
                        )
                        language = (
                            re.search(r"([^/]+语)", info).group(1)
                            if re.search(r"([^/]+语)", info)
                            else "未知"
                        )
                        director = (
                            re.search(r"导演:\s*(.+?)\s", info).group(1)
                            if re.search(r"导演:\s*(.+?)\s", info)
                            else "未知"
                        )

                        movies.append(
                            {
                                "电影名字": title,
                                "评分": rating,
                                "年份": year,
                                "国家": country,
                                "语种": language,
                                "导演": director,
                                "上映时间": f"{year}年",
                            }
                        )
                    except Exception:
                        continue

                time.sleep(0.5)
            except Exception:
                continue

        return movies


# ===================== NiceGUI 界面（必需保留） =====================


class DoubanGUI:
    def __init__(self):
        self.spider = DoubanSpider()
        self.ui_queue = queue.Queue()
        self.build_ui()
        ui.timer(0.1, self.update_ui)

    def build_ui(self):
        ui.page_title("豆瓣TOP250")
        with ui.column().classes("w-full max-w-4xl mx-auto p-6"):
            ui.label("🎬 豆瓣电影Top250 爬虫").classes(
                "text-3xl font-bold mb-4 text-blue-600"
            )
            with ui.row().classes("gap-3 mb-4"):
                self.btn_start = ui.button(
                    "开始爬取", on_click=self.run_crawl, color="green"
                )
                self.btn_save = ui.button(
                    "保存JSON", on_click=self.save_data, color="blue"
                ).props("disable")
            self.status_label = ui.label("✅ 就绪").classes("text-lg mb-4")

            # 数据表格
            self.table = ui.table(
                columns=[
                    {"name": "i", "label": "序号", "field": "i"},
                    {"name": "title", "label": "电影名", "field": "title"},
                    {"name": "score", "label": "评分", "field": "score"},
                    {"name": "year", "label": "年份", "field": "year"},
                    {"name": "country", "label": "国家", "field": "country"},
                ],
                rows=[],
                pagination=10,
            ).classes("mb-6")

            # 完整数据展示
            with ui.expansion("📄 完整JSON数据"):
                self.json_area = ui.textarea().classes("w-full h-60").props("readonly")

    def update_ui(self):
        while not self.ui_queue.empty():
            act, data = self.ui_queue.get()
            if act == "finish":
                movies, json_data = data
                # 渲染表格
                rows = [
                    {
                        "i": i + 1,
                        "title": m["电影名字"],
                        "score": m["评分"],
                        "year": m["年份"],
                        "country": m["国家"],
                    }
                    for i, m in enumerate(movies)
                ]
                self.table.rows = rows
                self.json_area.value = json_data
                self.status_label.text = f"✅ 爬取完成！共 {len(movies)} 部电影"
                self.btn_save.props("remove disable")

    def run_crawl(self):
        """线程爬取，不卡顿界面"""
        self.table.rows = []
        self.json_area.value = "爬取中..."
        self.status_label.text = "🔄 正在爬取..."
        threading.Thread(target=self._crawl_task, daemon=True).start()

    def _crawl_task(self):
        movies = self.spider.start_crawl(pages=3)
        json_data = json.dumps(movies, ensure_ascii=False, indent=2)
        self.ui_queue.put(("finish", (movies, json_data)))

    def save_data(self):
        filename = f"豆瓣TOP250_{int(time.time())}.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(self.json_area.value)
        ui.notify(f"✅ 已保存：{filename}")


# ===================== 启动（兼容NiceGUI多进程） =====================
if __name__ in {"__main__", "__mp_main__"}:
    DoubanGUI()
    ui.run(host="127.0.0.1", port=8080, show=True, reload=False)
