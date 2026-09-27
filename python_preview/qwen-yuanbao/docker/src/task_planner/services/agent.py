"""
agent.py — Agent 主入口（LangGraph 驱动版）

支持两种执行模式：
  - 新建任务: run_task_stream(user_input, thread_id)
  - 断点续传: run_task_stream("", thread_id, resume=True)
    从 LangGraph checkpoint 恢复状态并继续 stream
"""
from __future__ import annotations
import queue
import threading
import time
import traceback
from typing import Any, Generator

from task_planner.utils.context import cancel_event_var
from task_planner.core.graph.nodes import _sanitize_input
from task_planner.infrastructure.logger_setup import get_logger, set_req_id
from task_planner.core.graph.workflow import graph
from task_planner.core.graph.state import TaskState, UserAction
from task_planner.infrastructure.config import SKIP_PLANNING_PATTERNS, SESSION_TTL

logger = get_logger(__name__)
_SESSION_TTL = SESSION_TTL
_SKIP_PLANNING_PATTERNS = SKIP_PLANNING_PATTERNS
# ══════════════════════════════════════════════════
#  活跃任务管理
# ══════════════════════════════════════════════════

_active_sessions: dict[str, dict[str, Any]] = {}
_sessions_lock = threading.Lock()


class TaskSession:
    """单个任务会话 - 运行时对象与序列化配置彻底分离"""

    def __init__(self, thread_id: str, user_input: str):
        self.thread_id = thread_id
        self.user_input = user_input

        # ✅ 运行时对象只作为实例属性，绝不放入 config / state
        self.cancel_event = threading.Event()
        self.progress_q: queue.Queue = queue.Queue()
        self.start_time = time.time()

        # ✅ config 保持纯净，只放可序列化的元数据
        self.config: dict[str, Any] = {
            "configurable": {
                "thread_id": thread_id,
            }
        }

    def emit(self, msg: str) -> None:
        self.progress_q.put(msg)
        logger.info("[Agent] %s", msg)


def get_session(thread_id: str) -> TaskSession | None:
    with _sessions_lock:
        entry = _active_sessions.get(thread_id)
        if not entry:
            return None
        # ✅ 修复1: _time → time
        if time.time() - entry["start_time"] > _SESSION_TTL:
            _active_sessions.pop(thread_id, None)
            logger.warning("[Agent] 清理过期 session: %s", thread_id)
            return None
        return entry["session"]


def cleanup_stale_sessions() -> int:
    """定期清理，可由定时任务或请求入口调用"""
    now = time.time()  # ✅ 修复1: _time → time
    stale = []
    with _sessions_lock:
        for tid, entry in _active_sessions.items():
            if now - entry["start_time"] > _SESSION_TTL:
                stale.append(tid)
        for tid in stale:
            del _active_sessions[tid]
    if stale:
        logger.info("[Agent] 清理 %d 个过期 session", len(stale))
    return len(stale)


# ══════════════════════════════════════════════════
#  初始状态构建
# ══════════════════════════════════════════════════

def _should_skip_planning(user_input: str) -> bool:
    """显式拒绝规划的正则拦截（最高优先级）"""
    for pattern in _SKIP_PLANNING_PATTERNS:
        if pattern.search(user_input):
            logger.info("[Agent] 显式拒绝规划命中: %s", pattern.pattern)
            return True
    return False


def _make_initial_state(user_input: str, thread_id: str) -> TaskState:
    """构建初始状态，含显式拒绝规划拦截"""
    skip_planning = _should_skip_planning(user_input)

    if skip_planning:
        logger.info("[Agent] 关键词/正则拦截：用户明确要求跳过规划")

    return TaskState(
        messages=[],
        user_input=user_input,
        thread_id=thread_id,
        intent={},
        needs_planning=not skip_planning,
        plan={},
        nodes=[],
        edges=[],
        refined_nodes=[],
        task_id="",
        current_node_index=0,
        node_results=[],
        svg="",
        # ✅ 关键：拦截时预置标记，确保 Graph 有明确降级路径
        direct_response="__DIRECT_RESPONSE_PENDING__" if skip_planning else "",
        cancel_requested=False,
        error="",
        status_text="",
        steps=["跳过规划：用户显式拒绝"] if skip_planning else [],
        user_action=None,
        modified_input=None,
        retry_node_id=None,
    )


# ══════════════════════════════════════════════════
#  核心流式执行
# ══════════════════════════════════════════════════

def run_task_stream(
    user_input: str,
    thread_id: str,
    enable_refine: bool = True,
    resume: bool = False,
) -> Generator[dict[str, Any], None, None]:
    """启动任务，以 Generator 方式实时推送进度。"""
    if not isinstance(thread_id, str):
        raise TypeError(
            f"thread_id must be str, got {type(thread_id).__name__}: {
                thread_id!r}"
        )

    rid = set_req_id()
    logger.info("[Agent] 启动任务 | thread=%s req=%s", thread_id, rid)

    session = TaskSession(thread_id, user_input)
    with _sessions_lock:
        _active_sessions[thread_id] = {
            "session": session,
            "start_time": session.start_time,
        }

    # ✅ 修复3: 设置 ContextVar，确保当前线程的节点函数能取到 cancel_event
    token = cancel_event_var.set(session.cancel_event)

    try:
        event_count = 0

        if resume:
            # ═══ 断点续传模式：不传 initial_state，从 checkpoint 继续 ═══
            logger.info("[Agent] resume 模式 | thread=%s", thread_id)
            stream_iter = graph.stream(
                None,  # ← None 表示从 checkpoint 恢复
                session.config,
                stream_mode=["values", "updates"],
            )
        else:
            # ═══ 新建任务模式 ═══
            initial_state = _make_initial_state(user_input, thread_id)
            logger.info("[Agent] initial_state keys: %s",
                        list(initial_state.keys()))
            state_dict = dict(initial_state)
            stream_iter = graph.stream(
                state_dict,
                session.config,
                stream_mode=["values", "updates"],
            )

        for event in stream_iter:
            event_count += 1

            # 解包组合模式的事件
            if isinstance(event, tuple):
                mode, data = event
                logger.info("[Agent] event #%d [%s] received",
                            event_count, mode)
            else:
                mode, data = "values", event
                logger.info("[Agent] event #%d received", event_count)

            # 检查取消
            if session.cancel_event.is_set():
                logger.info("[Agent] 收到取消信号 (req=%s)", rid)
                break

            snapshot = _extract_snapshot(data, session, mode=mode)
            if snapshot is not None:
                yield snapshot

            # ✅ 修复6: 不再每次调用 graph.get_state()，改用轻量级判断
            if _is_graph_finished(data, mode):
                break

        logger.info("[Agent] graph.stream() 结束，共 %d 个事件", event_count)

    except Exception as exc:
        logger.error("[Agent] 异常: %s\n%s", exc, traceback.format_exc())
        yield {
            "type": "error",
            "error": str(exc),
            "task_id": session.config["configurable"]["thread_id"],
        }
    finally:
        # ✅ 确保取消信号已设置，防止 Generator 被 GC 回收后图在后台空跑
        session.cancel_event.set()
        # ✅ 修复3: 恢复 ContextVar，避免线程复用时泄漏
        try:
            cancel_event_var.reset(token)
        except ValueError:
            pass
        with _sessions_lock:
            _active_sessions.pop(thread_id, None)
        logger.info(
            "[Agent] session cleaned up | thread=%s req=%s", thread_id, rid
        )

# ══════════════════════════════════════════════════
#  命令操作（取消 / 修改 / 继续 / 重试）
# ══════════════════════════════════════════════════


def cancel_task(thread_id: str) -> bool:
    """取消任务"""
    session = get_session(thread_id)
    if session:
        session.cancel_event.set()
        logger.info("[Agent] 取消信号已发送 | thread=%s", thread_id)
        return True
    return False


def _resume_with_command(
    session: TaskSession,
    resume_data: dict[str, Any],
) -> None:
    """
    统一的 resume 执行入口。

    ✅ 修复4: invoke 前必须设置 ContextVar，否则被 resume 的节点
       在执行时 cancel_event_var.get() 返回 None，取消信号丢失
    """
    token = cancel_event_var.set(session.cancel_event)
    try:
        from langgraph.types import Command
        graph.invoke(Command(resume=resume_data), session.config)
    finally:
        try:
            cancel_event_var.reset(token)
        except ValueError:
            pass


def modify_task(thread_id: str, new_input: str) -> bool:
    """修改任务需求"""
    session = get_session(thread_id)
    if not session:
        return False

    try:
        cleaned = _sanitize_input(new_input)
    except ValueError as e:
        logger.warning("[Agent] 修改输入校验失败: %s", e)
        return False

    _resume_with_command(session, {
        "action": UserAction.MODIFY,
        "user_input": cleaned,
    })
    return True


def resume_task(thread_id: str) -> bool:
    """继续执行（用户点"继续"）"""
    session = get_session(thread_id)
    if not session:
        return False

    _resume_with_command(session, {
        "action": UserAction.CONTINUE,
    })
    return True


def retry_node_cmd(thread_id: str, node_id: int) -> bool:
    """重试指定节点"""
    session = get_session(thread_id)
    if not session:
        return False

    _resume_with_command(session, {
        "action": UserAction.RETRY_NODE,
        "node_id": node_id,
    })
    return True


# ══════════════════════════════════════════════════
#  内部工具
# ══════════════════════════════════════════════════


def _extract_snapshot(
    event: dict[str, Any],
    session: TaskSession,
    mode: str = "values",
) -> dict[str, Any] | None:
    """从 graph event 中提取前端需要的快照"""
    elapsed = time.time() - session.start_time

    if mode == "updates":
        # updates 模式下 data 是 {node_name: {field_updates}}
        # 前端通常只需要 values 模式的完整快照，updates 可跳过
        return None

    return {
        "type": "progress",
        "task_id": event.get("task_id", ""),
        "svg": event.get("svg", ""),
        "flowchart_html": event.get("flowchart_html", ""),
        "direct_response": event.get("direct_response", ""),
        "status_text": event.get("status_text", ""),
        "steps": event.get("steps", []),
        "error": event.get("error", ""),
        "cancel_requested": event.get("cancel_requested", False),
        "current_node_index": event.get("current_node_index", 0),
        "node_results": event.get("node_results", []),
        "needs_planning": event.get("needs_planning", True),
        "view_mode": event.get("view_mode"),
        "elapsed": round(elapsed, 1),
        "nodes": event.get("nodes") or [],
        "edges": event.get("edges") or [],
    }


def _is_graph_finished(event_data: dict[str, Any], mode: str) -> bool:
    """
    轻量级完成判断。

    ✅ 不再调用 graph.get_state()（每次都要读 checkpoint），
       改为检查 event 数据中的终止信号。
    ✅ resume 模式下 direct_response 不作为终止条件
       （恢复执行时可能携带历史 direct_response）
    """
    if mode != "values":
        return False

    # 取消 → 视为结束
    if event_data.get("cancel_requested"):
        return True

    # 显式错误 → 视为结束
    if event_data.get("error"):
        return True

    # 所有节点执行完毕
    nodes = event_data.get("nodes", [])
    idx = event_data.get("current_node_index", 0)
    if nodes and idx >= len(nodes):
        return True

    # 直接回答模式（仅在新建任务时作为终止条件）
    # resume 模式下 direct_response 可能是历史残留，不据此终止
    direct_resp = event_data.get("direct_response", "")
    if direct_resp and direct_resp != "__DIRECT_RESPONSE_PENDING__":
        # 检查是否有规划节点：有节点说明是规划任务，不以 direct_response 终止
        if not nodes:
            return True

    return False


# 向后兼容
task_agent = None  # 不再使用旧的单例模式
