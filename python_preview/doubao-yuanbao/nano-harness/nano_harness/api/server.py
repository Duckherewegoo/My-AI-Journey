"""
REST API 服务端
===============
基于FastAPI的REST API服务。

提供完整的HTTP接口，支持：
- 对话聊天
- 任务管理
- Skill管理
- MCP协议接入
- WebSocket流式输出
"""


"""
REST API 服务端
===============
基于FastAPI的REST API服务。
提供完整的HTTP接口，支持：
- 对话聊天
- 任务管理
- Skill管理
- MCP协议接入
- WebSocket流式输出
"""


# ===== 全局配置初始化 =====
# 初始化日志
import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
from asyncio import Lock, to_thread, wait_for, TimeoutError
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 任务超时配置（秒）
TASK_TIMEOUT = 30.0

# ===== 请求/响应模型 =====


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID，用于多轮对话")
    stream: bool = Field(False, description="是否流式输出")


class ChatResponse(BaseModel):
    """对话响应"""
    response: str = Field(..., description="AI回复")
    session_id: str = Field(..., description="会话ID")
    task_id: Optional[str] = Field(None, description="任务ID（如果触发了任务）")
    timestamp: str = Field(..., description="时间戳")


class TaskCreateRequest(BaseModel):
    """创建任务请求"""
    description: str = Field(..., description="任务描述")
    priority: str = Field("normal", description="优先级：low/normal/high")


class TaskResponse(BaseModel):
    """任务响应"""
    task_id: str = Field(..., description="任务ID")
    description: str = Field(..., description="任务描述")
    status: str = Field(..., description="任务状态")
    result: Optional[str] = Field(None, description="任务结果")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")


class SkillInfo(BaseModel):
    """Skill信息"""
    name: str
    description: str
    version: str
    category: str
    tags: List[str]
    tool_count: int


class MCPToolCallRequest(BaseModel):
    """MCP工具调用请求"""
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)

# ===== API服务 =====


def create_app(harness=None) -> FastAPI:
    """
    创建FastAPI应用

    Args:
        harness: Harness实例（可选）

    Returns:
        FastAPI应用实例
    """
    app = FastAPI(
        title="NanoHarness API",
        description="轻量级多智能体编排框架 - REST API",
        version="1.0.0",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 存储任务状态 + 异步锁保护并发读写（修复：无锁竞态条件问题）
    tasks: Dict[str, Dict] = {}
    sessions: Dict[str, Dict] = {}
    task_lock = Lock()
    session_lock = Lock()

    # ===== 根路径 =====

    @app.get("/")
    async def root():
        """API信息"""
        return {
            "name": "NanoHarness API",
            "version": "1.0.0",
            "description": "轻量级多智能体编排框架",
            "endpoints": {
                "chat": "/api/v1/chat",
                "tasks": "/api/v1/tasks",
                "skills": "/api/v1/skills",
                "mcp": "/api/v1/mcp",
            },
        }

    @app.get("/health")
    async def health():
        """健康检查"""
        return {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "harness_loaded": harness is not None,
        }

    # ===== 对话接口 =====

    @app.post("/api/v1/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """
        对话接口

        发送消息给AI，获取回复。
        支持多轮对话（通过session_id）。
        """
        session_id = request.session_id or str(uuid.uuid4())

        # 如果有harness实例，使用它
        if harness:
            try:
                # 修复：同步函数放入线程池执行，避免阻塞事件循环（核心异步/同步混用问题）
                result = await to_thread(harness.run, request.message)
                response_text = result.get("final_output", str(result))
                task_id = result.get("task_id")
            except Exception as e:
                response_text = f"处理出错：{str(e)}"
                task_id = None
                logger.error(f"对话接口处理异常：{str(e)}", exc_info=True)
        else:
            # 没有harness时的模拟回复
            response_text = (
                f"收到消息：{request.message}\n\n"
                f"[提示] 当前为API演示模式。配置Harness实例后可获得完整AI能力。\n\n"
                f"可用功能：\n"
                f"- 多智能体协作（规划/执行/评审/协调）\n"
                f"- Skill插件系统\n"
                f"- MCP协议支持\n"
                f"- 多模态处理（图片/视频/音频）\n"
                f"- Bash命令执行（带用户确认）\n"
            )
            task_id = None

        # 修复：加锁保护会话数据写入，避免并发竞态
        async with session_lock:
            sessions[session_id] = {
                "last_message": request.message,
                "last_response": response_text,
                "updated_at": datetime.now().isoformat(),
            }

        return ChatResponse(
            response=response_text,
            session_id=session_id,
            task_id=task_id,
            timestamp=datetime.now().isoformat(),
        )

    # ===== 任务接口 =====

    @app.post("/api/v1/tasks", response_model=TaskResponse)
    async def create_task(request: TaskCreateRequest):
        """创建任务"""
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        task = {
            "task_id": task_id,
            "description": request.description,
            "priority": request.priority,
            "status": "pending",
            "result": None,
            "created_at": now,
            "updated_at": now,
        }

        # 修复：加锁保护任务数据写入
        async with task_lock:
            tasks[task_id] = task

        # 如果有harness，异步执行（传入锁对象保证线程安全）
        if harness:
            asyncio.create_task(_run_task_async(
                task_id, task, task_lock, harness))

        # 修复：Pydantic v2 标准写法，替代旧版直接解包
        return TaskResponse.model_validate(task)

    async def _run_task_async(task_id: str, task: Dict, lock: Lock, harness_instance):
        """异步执行任务（修复：新增超时控制、线程池调用、日志记录、线程安全写操作）"""
        try:
            # 加锁更新任务状态
            async with lock:
                task["status"] = "running"
                task["updated_at"] = datetime.now().isoformat()

            if harness_instance:
                logger.info(f"任务 {task_id} 开始执行")
                # 同步函数放入线程池 + 超时控制，避免阻塞事件循环和任务无限执行
                result = await wait_for(
                    to_thread(harness_instance.run, task["description"]),
                    timeout=TASK_TIMEOUT
                )
                async with lock:
                    task["result"] = str(result)
                    task["status"] = "completed"
                logger.info(f"任务 {task_id} 执行完成")
            else:
                async with lock:
                    task["result"] = "演示模式：任务已模拟完成"
                    task["status"] = "completed"
        except TimeoutError:
            async with lock:
                task["result"] = f"任务执行超时（上限{TASK_TIMEOUT}秒）"
                task["status"] = "failed"
            logger.error(f"任务 {task_id} 执行超时")
        except Exception as e:
            async with lock:
                task["result"] = f"任务失败：{str(e)}"
                task["status"] = "failed"
            logger.error(f"任务 {task_id} 执行异常：{str(e)}", exc_info=True)

        # 统一更新时间
        async with lock:
            task["updated_at"] = datetime.now().isoformat()

    @app.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str):
        """查询任务状态"""
        if task_id not in tasks:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 修复：Pydantic v2 标准写法
        return TaskResponse.model_validate(tasks[task_id])

    @app.get("/api/v1/tasks")
    async def list_tasks(status: Optional[str] = None):
        """列出任务"""
        result = list(tasks.values())

        if status:
            result = [t for t in result if t["status"] == status]

        return {
            "total": len(result),
            "tasks": result,
        }

    # ===== Skill接口 =====

    @app.get("/api/v1/skills", response_model=List[SkillInfo])
    async def list_skills():
        """列出所有已注册的Skill"""
        if not harness or not hasattr(harness, 'skill_registry'):
            return []

        skills = []
        for skill_name in harness.skill_registry.get_skill_names():
            skill = harness.skill_registry.get_skill(skill_name)
            tools = skill.get_tools() if hasattr(skill, 'get_tools') else []

            skills.append(SkillInfo(
                name=skill.name,
                description=skill.description,
                version=skill.version,
                category=getattr(skill, 'category', 'unknown'),
                tags=getattr(skill, 'tags', []),
                tool_count=len(tools),
            ))

        return skills

    @app.get("/api/v1/skills/{skill_name}")
    async def get_skill(skill_name: str):
        """获取Skill详细信息"""
        if not harness or not hasattr(harness, 'skill_registry'):
            raise HTTPException(status_code=404, detail="Skill注册中心未配置")

        skill = harness.skill_registry.get_skill(skill_name)
        if not skill:
            raise HTTPException(
                status_code=404, detail=f"Skill不存在：{skill_name}")

        tools = skill.get_tools() if hasattr(skill, 'get_tools') else []
        tool_names = [t.name for t in tools] if tools else []

        return {
            "name": skill.name,
            "description": skill.description,
            "version": skill.version,
            "author": getattr(skill, 'author', 'unknown'),
            "category": getattr(skill, 'category', 'unknown'),
            "tags": getattr(skill, 'tags', []),
            "tools": tool_names,
            "tool_count": len(tool_names),
        }

    # ===== MCP接口 =====

    @app.get("/api/v1/mcp/tools")
    async def list_mcp_tools():
        """列出MCP可用工具"""
        if not harness or not hasattr(harness, 'mcp_server'):
            return {
                "tools": [],
                "message": "MCP服务未配置",
            }

        tools = harness.mcp_server.list_tools()
        return {
            "tools": tools,
            "count": len(tools),
        }

    @app.post("/api/v1/mcp/call")
    async def call_mcp_tool(request: MCPToolCallRequest):
        """调用MCP工具"""
        if not harness or not hasattr(harness, 'mcp_server'):
            raise HTTPException(status_code=503, detail="MCP服务未配置")

        try:
            # 修复：同步工具调用放入线程池，避免阻塞
            result = await to_thread(
                harness.mcp_server.call_tool,
                request.tool_name,
                request.arguments,
            )
            return {
                "tool": request.tool_name,
                "result": result,
                "success": True,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ===== WebSocket =====

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        """WebSocket实时对话（修复：新增异常捕获、会话清理、线程池调用）"""
        await websocket.accept()
        session_id = str(uuid.uuid4())
        logger.info(f"WebSocket 连接建立：{session_id}")

        try:
            while True:
                # 修复：捕获JSON格式错误，避免连接直接断开
                try:
                    data = await websocket.receive_json()
                except ValueError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "无效的JSON格式",
                        "session_id": session_id,
                    })
                    continue

                message = data.get("message", "")

                # 发送思考中状态
                await websocket.send_json({
                    "type": "status",
                    "status": "thinking",
                    "session_id": session_id,
                })

                # 修复：同步逻辑放入线程池，避免阻塞WebSocket事件循环
                try:
                    if harness:
                        result = await to_thread(harness.run, message)
                        response = str(result)
                    else:
                        response = f"[演示模式] 收到：{message}"
                except Exception as e:
                    response = f"错误：{str(e)}"
                    logger.error(f"WebSocket 消息处理异常：{str(e)}", exc_info=True)

                # 发送回复
                await websocket.send_json({
                    "type": "message",
                    "content": response,
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat(),
                })

        except WebSocketDisconnect:
            logger.info(f"WebSocket 连接断开：{session_id}")
        finally:
            # 修复：连接断开后清理会话数据，避免内存泄漏
            async with session_lock:
                sessions.pop(session_id, None)

    # ===== 挂载静态文件（Web UI）=====
    # 修复：用 pathlib 替代旧版 os.path，跨平台更稳定，路径层级更清晰
    current_dir = Path(__file__).absolute().parent
    web_dir = current_dir.parent.parent / "web"
    if web_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(web_dir),
                  html=True), name="web")

    return app


def run_server(
    harness=None,
    host: str = "0.0.0.0",
    port: int = 8000,
    **kwargs,
):
    """
    运行API服务器

    Args:
        harness: Harness实例
        host: 监听地址
        port: 监听端口
    """
    import uvicorn

    app = create_app(harness)

    print(f"🚀 NanoHarness API 启动中...")
    print(f"📡 地址：http://{host}:{port}")
    print(f"📚 API文档：http://{host}:{port}/docs")
    print(f"🌐 Web界面：http://{host}:{port}/ui")
    print()

    uvicorn.run(app, host=host, port=port, **kwargs)
