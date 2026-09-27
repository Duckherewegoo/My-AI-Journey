import os
import json
import uuid
import threading
import time
from datetime import datetime
from pathlib import Path

# ================= 1. 依赖导入 =================
import dashscope
from dashscope import Generation
import networkx as nx
import matplotlib.pyplot as plt
from pymongo import MongoClient
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
from flask import Flask, render_template_string, send_from_directory
import gradio as gr
import requests

# ================= 2. 全局配置与初始化 =================
# 设置 Matplotlib 中文字体，防止中文显示为方块
plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'SimHei',
                                   'Arial Unicode MS', 'Microsoft YaHei', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
# 初始化数据库 (MongoDB)
try:
    mongo_client = MongoClient(
        MONGO_URI, serverSelectionTimeoutMS=2000)
    mongo_client.server_info()
    db = mongo_client["task_planner"]
    print("✅ 成功连接到 MongoDB")
except Exception as e:
    print(f"⚠️ MongoDB 连接失败 ({e})，自动切换为内存字典模拟数据库...")

    class MockCollection:
        def __init__(self): self.data = []
        def insert_one(self, doc): self.data.append(doc)
        def find(self): return self.data

    class MockDB:
        def __init__(self): self.task_graphs = MockCollection()
    db = MockDB()

# 确保图片保存目录存在
IMAGE_DIR = "images"
Path(IMAGE_DIR).mkdir(exist_ok=True)

# ================= 3. LLM 与 Prompt 设计 =================
SYSTEM_PROMPT = """你是一个高级任务规划与拆解专家。你的任务是将用户输入的复杂任务计划分解为具体的子任务，并梳理它们之间的依赖关系。
请严格以JSON格式输出你的规划结果，不要包含任何多余的解释、前言或后语，不要使用Markdown代码块标记（如```json）。
JSON结构必须严格遵循以下格式：
{
  "graph_title": "简明扼要的任务图标题",
  "nodes": [
    {
      "id": "唯一标识符，如task_1",
      "label": "子任务的具体名称或描述",
      "status": "pending",
      "cycle": "once",
      "time": "2023-10-01 09:00",
      "modify_flag": false,
      "valid_flag": true
    }
  ],
  "edges": [
    {
      "source": "前置任务的id",
      "target": "后置任务的id"
    }
  ]
}
要求：
1. nodes中的id必须全局唯一。
2. edges表示任务的执行先后顺序，source节点必须在target节点之前执行。
3. 确保输出的JSON格式完全合法，能够被Python的json.loads()直接解析。
"""


def call_llm(task_plan: str) -> str:
    """调用 DashScope Qwen 模型"""
    dashscope.api_key = os.getenv("DASHSCOPE_API_KEY")
    if not dashscope.api_key:
        raise ValueError("未找到环境变量 DASHSCOPE_API_KEY，请先配置。")

    response = Generation.call(
        model='qwen-turbo',
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': f"任务计划：{task_plan}"}
        ],
        result_format='message'
    )
    if response.status_code == 200:
        return response.output.choices[0].message.content
    else:
        raise Exception(f"LLM调用失败: {response.code} - {response.message}")


def clean_json_string(json_str: str) -> str:
    """清洗 LLM 返回的 JSON 字符串，去除可能的 Markdown 标记"""
    json_str = json_str.strip()
    if json_str.startswith("```json"):
        json_str = json_str[7:]
    elif json_str.startswith("```"):
        json_str = json_str[3:]
    if json_str.endswith("```"):
        json_str = json_str[:-3]
    return json_str.strip()

# ================= 4. 图绘制模块 =================


def draw_and_save_graph(task_data: dict, task_id: str) -> str:
    """使用 NetworkX 绘制有向图并保存为 PNG"""
    G = nx.DiGraph()
    nodes = task_data.get("nodes", [])
    edges = task_data.get("edges", [])

    for node in nodes:
        G.add_node(node["id"], label=node["label"])
    for edge in edges:
        G.add_edge(edge["source"], edge["target"])

    pos = nx.spring_layout(G, k=0.5, iterations=50)
    plt.figure(figsize=(12, 9))

    # 绘制节点
    labels = {node["id"]: node["label"] for node in nodes}
    nx.draw_networkx_nodes(G, pos, node_size=2500, node_color="#AED6F1",
                           node_shape="o", alpha=0.9, edgecolors="#2980B9")
    nx.draw_networkx_labels(G, pos, labels, font_size=10, font_weight="bold")

    # 绘制边
    nx.draw_networkx_edges(G, pos, arrowstyle="-|>",
                           arrowsize=20, edge_color="#7F8C8D", width=2)

    plt.title(task_data.get("graph_title", "Task Graph"),
              fontsize=18, fontweight="bold", color="#2C3E50")
    plt.axis("off")

    file_path = os.path.join(IMAGE_DIR, f"{task_id}.png")
    plt.savefig(file_path, format="png", bbox_inches="tight", dpi=150)
    plt.close()
    return file_path


# ================= 5. FastAPI 后端 =================
fastapi_app = FastAPI()


class TaskRequest(BaseModel):
    task_plan: str


@fastapi_app.post("/api/generate")
async def generate_task_graph(req: TaskRequest):
    try:
        # 1. 调用 LLM
        llm_output = call_llm(req.task_plan)
        clean_output = clean_json_string(llm_output)
        task_data = json.loads(clean_output)

        # 2. 存入数据库
        task_id = str(uuid.uuid4())
        task_data["_id"] = task_id
        task_data["created_at"] = datetime.now().isoformat()
        db.task_graphs.insert_one(task_data)

        # 3. 绘制图片
        img_path = draw_and_save_graph(task_data, task_id)

        return {"task_id": task_id, "graph_title": task_data.get("graph_title"), "image_path": os.path.abspath(img_path)}
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM 返回的 JSON 格式解析失败，请重试。")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@fastapi_app.get("/api/image/{task_id}")
async def get_image(task_id: str):
    file_path = os.path.join(IMAGE_DIR, f"{task_id}.png")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="Image not found")


def run_fastapi():
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="error")


# ================= 6. Flask 辅助前端 =================
flask_app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>任务路径图看板</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f4f7f6; margin: 0; padding: 20px; color: #333; }
        h1 { text-align: center; color: #2c3e50; }
        .container { max-width: 1000px; margin: 0 auto; }
        .task-card { background: #fff; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 20px; }
        .task-card h2 { margin-top: 0; color: #2980b9; }
        .meta { color: #7f8c8d; font-size: 0.9em; margin-bottom: 15px; }
        img { width: 100%; max-width: 800px; display: block; margin: 15px auto; border: 1px solid #ddd; border-radius: 4px; }
        .btn { display: inline-block; padding: 8px 16px; background: #2980b9; color: #fff; text-decoration: none; border-radius: 4px; }
        .btn:hover { background: #3498db; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 历史任务路径图看板</h1>
        {% if not tasks %}
            <p style="text-align:center;">暂无历史任务，请前往 Gradio 界面生成。</p>
        {% endif %}
        {% for task in tasks %}
        <div class="task-card">
            <h2>{{ task.graph_title }}</h2>
            <div class="meta">
                <strong>ID:</strong> {{ task._id }} | 
                <strong>创建时间:</strong> {{ task.created_at }}
            </div>
            <img src="/images/{{ task._id }}.png" alt="Task Graph">
            <div style="text-align: center;">
                <a class="btn" href="/images/{{ task._id }}.png" download>下载 PNG 图片</a>
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


@flask_app.route("/")
def index():
    tasks = list(db.task_graphs.find())
    if hasattr(tasks, 'sort'):  # pymongo cursor
        tasks = tasks.sort("created_at", -1)
    else:  # mock list
        tasks = sorted(tasks, key=lambda x: x.get(
            "created_at", ""), reverse=True)
    return render_template_string(HTML_TEMPLATE, tasks=tasks)


@flask_app.route("/images/<path:filename>")
def serve_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


def run_flask():
    flask_app.run(port=5000, debug=False, use_reloader=False)

# ================= 7. Gradio 交互界面 =================


def gradio_generate(task_plan):
    if not task_plan.strip():
        return "⚠️ 请输入任务计划！", None

    try:
        response = requests.post(
            "http://127.0.0.1:8000/api/generate", json={"task_plan": task_plan})
        if response.status_code == 200:
            data = response.json()
            msg = f"✅ 生成成功！\n图标题：{data['graph_title']}\n任务ID：{data['task_id']}"
            return msg, data['image_path']
        else:
            return f"❌ 生成失败：{response.json().get('detail', response.text)}", None
    except Exception as e:
        return f"❌ 请求异常：{str(e)}", None


gradio_app = gr.Interface(
    fn=gradio_generate,
    inputs=gr.Textbox(
        lines=5,
        placeholder="请输入您的任务计划，例如：开发一个电商网站，包括需求分析、UI设计、前端开发、后端开发、测试和部署...",
        label="任务计划输入"
    ),
    outputs=[
        gr.Textbox(label="执行状态"),
        gr.Image(label="任务路径有向图", type="filepath")
    ],
    title="🚀 AI 任务路径图生成器",
    description="输入复杂任务计划，大模型将自动拆解任务依赖并生成有向图。生成的图片可在 Flask 看板中查看。",
)


def run_gradio():
    gradio_app.launch(server_name="127.0.0.1",
                      server_port=7860, share=False)


# ================= 8. 主启动逻辑 =================
if __name__ == "__main__":
    print("\n" + "="*40)
    print("🌟 启动 AI 任务路径图生成系统 🌟")
    print("="*40)

    # 启动后台服务
    threading.Thread(target=run_flask, daemon=True).start()
    print("👉 Flask 看板已启动: http://127.0.0.1:5000")

    threading.Thread(target=run_fastapi, daemon=True).start()
    print("👉 FastAPI 后端已启动: http://127.0.0.1:8000")

    print("👉 Gradio 交互界面启动中...")
    print("="*40 + "\n")

    # 主线程运行 Gradio
    run_gradio()
