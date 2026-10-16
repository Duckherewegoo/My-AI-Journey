"""
workflow.py — LangGraph 工作流定义（生产最终版）
"""
from __future__ import annotations

import os
import threading
from typing import Any

from langgraph.graph import END, START, StateGraph

from task_planner.core.graph.nodes import (
    cancel_node,
    direct_answer_node,
    execute_node,
    intent_node,
    plan_node,
    save_node,
    refine_node_fn,
    render_node,
    route_after_execute,
    route_after_intent,
    route_after_render,
)
from task_planner.core.graph.state import TaskState
from task_planner.infrastructure.logger_setup import get_logger

logger = get_logger(__name__)


def _build_checkpointer():
    """
    根据环境变量自动选择 checkpointer。

    CHECKPOINTER_TYPE: memory | sqlite | postgres
    默认: memory（开发友好）

    ⚠️ 生产环境注意事项：
    - sqlite: 仅适合单进程/低并发场景，高并发请用 postgres
    - postgres: 推荐生产使用，连接池由 PostgresSaver 内部管理
    - memory: 仅限开发调试，重启丢失所有状态
    """
    cp_type = os.getenv("CHECKPOINTER_TYPE", "memory").lower()

    if cp_type == "sqlite":
        from langgraph.checkpoint.sqlite import SqliteSaver
        import sqlite3

        db_path = os.getenv("CHECKPOINT_DB_PATH", "checkpoints.db")
        # ✅ WAL 模式 + busy_timeout 提升并发安全性
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return SqliteSaver(conn)

    elif cp_type == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        conn_str = os.getenv("CHECKPOINT_POSTGRES_URL", "")
        if not conn_str:
            raise ValueError(
                "CHECKPOINTER_TYPE=postgres 但未设置 CHECKPOINT_POSTGRES_URL"
            )
        # ✅ PostgresSaver.from_conn_string 内部自带连接池管理
        return PostgresSaver.from_conn_string(conn_str)

    else:
        from langgraph.checkpoint.memory import MemorySaver
        return MemorySaver()


def build_graph():
    """构建并编译 LangGraph"""
    builder = StateGraph(TaskState)

    # ── 添加节点 ──
    builder.add_node("intent", intent_node)
    builder.add_node("plan", plan_node)
    builder.add_node("refine", refine_node_fn)
    builder.add_node("save", save_node)
    builder.add_node("render", render_node)
    builder.add_node("execute", execute_node)
    builder.add_node("direct_answer", direct_answer_node)
    builder.add_node("cancel", cancel_node)

    def _route_start(state: TaskState) -> str:
        rid = state.get("req_id", "?")
        if not state.get("needs_planning", True):
            logger.info(
                "[Workflow] START → direct_answer (needs_planning=False, req=%s)", rid)
            return "direct_answer"
        logger.info(
            "[Workflow] START → intent (needs_planning=True, req=%s)", rid)
        return "intent"

    builder.add_conditional_edges(
        START,
        _route_start,
        {
            "direct_answer": "direct_answer",
            "intent": "intent",
        },
    )

    # ── 意图识别后路由（保持不变）──
    builder.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "plan": "plan",
            "direct_answer": "direct_answer",
            "cancel": "cancel",
        },
    )

    # ── 规划 → 细化 → 入库 → 渲染 ──
    builder.add_edge("plan", "refine")
    builder.add_edge("refine", "save")
    builder.add_edge("save", "render")

    # ── 渲染后 → 执行 ──
    builder.add_conditional_edges(
        "render",
        route_after_render,
        {"execute": "execute"},
    )

    # ── 执行后路由 ──
    builder.add_conditional_edges(
        "execute",
        route_after_execute,
        {
            "execute": "execute",
            "intent": "intent",
            "finish": END,
            "cancel": "cancel",
        },
    )

    # ── 终止边 ──
    builder.add_edge("direct_answer", END)
    builder.add_edge("cancel", END)

    # ── 编译（带 checkpoint）──
    checkpointer = _build_checkpointer()
    return builder.compile(checkpointer=checkpointer)

# ══════════════════════════════════════════════════
#  ✅ 断点续传：基于已有 thread_id 恢复执行
# ══════════════════════════════════════════════════


def resume_graph(
    thread_id: str,
    user_action: str = "continue",
    modified_input: str | None = None,
    target_node_index: int | None = None,
) -> dict[str, Any]:
    """
    从 checkpoint 恢复历史任务并继续执行。

    Args:
        thread_id: 历史会话的 thread_id（即 task_id 或 uuid）
        user_action: 用户指令 ("continue" | "modify" | "retry_node" | "cancel")
        modified_input: 当 user_action="modify" 时传入新的用户需求
        target_node_index: 当需要跳转到指定节点时传入索引

    Returns:
        恢复后的最新 state 快照
    """
    g = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 获取当前 checkpoint 状态
    snapshot = g.get_state(config)
    if not snapshot or not snapshot.values:
        raise ValueError(f"未找到 thread_id={thread_id} 的历史状态，无法恢复")

    logger.info(
        "[Workflow] resume_graph: thread=%s, action=%s, next_nodes=%s",
        thread_id, user_action, snapshot.next,
    )

    # 2. 构造 interrupt 反馈（模拟用户在 execute_node 中的 interrupt 响应）
    feedback: dict[str, Any] = {"action": user_action}
    if user_action == "modify" and modified_input:
        feedback["user_input"] = modified_input
    if target_node_index is not None:
        feedback["target_node_index"] = target_node_index

    # 3. 通过 update_state 注入反馈，触发 LangGraph 从 interrupt 点继续
    #    LangGraph 的 interrupt 机制要求用 as_node="execute" 指定恢复节点
    g.update_state(config, feedback, as_node="execute")

    # 4. 继续执行后续节点（stream 模式由上层 stream_manager 处理）
    #    这里仅返回恢复后的状态快照，实际执行由调用方决定 invoke/stream
    new_snapshot = g.get_state(config)
    return {
        "thread_id": thread_id,
        "state": new_snapshot.values if new_snapshot else {},
        "next_nodes": new_snapshot.next if new_snapshot else [],
    }


def get_thread_state(thread_id: str) -> dict[str, Any] | None:
    """
    安全获取指定 thread 的 checkpoint 状态。
    用于前端判断是否可以续传、当前进度等。
    """
    g = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = g.get_state(config)
        if not snapshot or not snapshot.values:
            return None
        return {
            "thread_id": thread_id,
            "state": snapshot.values,
            "next_nodes": snapshot.next,
            "has_checkpoint": True,
        }
    except Exception as e:
        logger.warning("[Workflow] get_thread_state failed: %s", e)
        return None

# ══════════════════════════════════════════════════
#  ✅ 懒加载单例：避免 import 时副作用
# ══════════════════════════════════════════════════


_graph_instance: Any = None
_graph_lock = threading.Lock()


def get_graph():
    """
    获取全局 graph 实例（线程安全懒加载）。

    用法:
        from .workflow import get_graph
        graph = get_graph()
        result = graph.invoke(...)
    """
    global _graph_instance
    if _graph_instance is None:
        with _graph_lock:
            if _graph_instance is None:
                _graph_instance = build_graph()
    return _graph_instance


class _LazyGraphProxy:
    """代理对象，首次属性访问时才真正构建 graph"""

    def __getattr__(self, name: str):
        return getattr(get_graph(), name)

    def __call__(self, *args, **kwargs):
        return get_graph()(*args, **kwargs)

    # ✅ 调试友好：打印时显示真实类型而非 <_LazyGraphProxy>
    def __repr__(self) -> str:
        if _graph_instance is not None:
            return f"<LazyGraphProxy → {type(_graph_instance).__name__} (initialized)>"
        return "<LazyGraphProxy → CompiledGraph (not yet initialized)>"


graph: Any = _LazyGraphProxy()

# ══════════════════════════════════════════════════
#  ✅ 公开 API：供 stream_manager / dash_app 调用
# ══════════════════════════════════════════════════

__all__ = [
    "build_graph",
    "get_graph",
    "resume_graph",
    "get_thread_state",
    "graph",
]
