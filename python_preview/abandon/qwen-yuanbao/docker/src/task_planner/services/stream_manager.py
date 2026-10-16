"""
stream_manager.py — 后台流式任务管理 + 节点状态控制 (生产级重构版)
════════════════════════════════════════════════════════════════════
职责：
  ✅ 在后台线程中跑 run_task_stream() Generator
  ✅ 每次 yield 的 snapshot 存入 TaskStreamState
  ✅ Dash Interval 轮询时读取最新快照
  ✅ 统一由 StreamStateCleaner 守护线程管理生命周期与内存回收
  ✅ 节点状态字典管理（done/running/failed/skipped）与级联操作

设计原则：
  单例管理 + 线程安全 + TTL 兜底 + 零阻塞 UI
"""
import time
import threading
from typing import Any, Callable
from collections import deque

from task_planner.services.agent import cancel_task
from task_planner.core.graph.workflow import resume_graph, get_thread_state
from task_planner.utils.cytoscape_adapter import dag_to_cytoscape
from task_planner.infrastructure.logger_setup import get_logger

logger = get_logger("task_planner.stream_manager")


# ══════════════════════════════════════════════════
#  1. 单任务状态实体
# ══════════════════════════════════════════════════

class TaskStreamState:
    """单个流式任务的状态快照 + 节点状态"""

    def __init__(self, thread_id: str, ttl: int = 3600, max_snapshots: int = 100):
        self.thread_id = thread_id

        # 快照管理 (使用 deque 自动处理环形缓冲，比 list.pop(0) 高效)
        self.snapshots: deque[dict] = deque(maxlen=max_snapshots)
        self.latest: dict = {}

        # 生命周期状态
        self.finished: bool = False
        self.cancelled: bool = False
        self.error: str | None = None
        self._created_at: float = time.time()
        self._finished_at: float | None = None  # ✅ 关键：记录完成时间

        # 节点用户操作状态：{node_id: "done"|"running"|"failed"|"skipped"}
        self.node_states: dict[str, str] = {}

        # 线程锁：保护 latest, node_states, finished 等状态的并发读写
        self._lock = threading.Lock()
        self._ttl = ttl

    def is_expired(self, now: float | None = None) -> bool:
        """判断是否超时（未完成状态下）"""
        now = now or time.time()
        return not self.finished and (now - self._created_at > self._ttl)

    def push(self, snapshot: dict) -> None:
        """推入新快照，并同步节点状态"""
        with self._lock:
            # ═══ 防止关键字段在中间快照中被清空 (状态继承) ═══
            for key in ("nodes", "edges", "direct_response", "flowchart_html", "task_id"):
                if not snapshot.get(key) and self.latest.get(key):
                    snapshot[key] = self.latest[key]

            self.snapshots.append(snapshot)
            self.latest = snapshot
            self._sync_node_states(snapshot)

    def _sync_node_states(self, snap: dict) -> None:
        """从 snapshot 的 nodes/node_results 字段同步状态 (内部调用，已持锁)"""
        nodes = snap.get("nodes") or []
        current_idx = snap.get("current_node_index", 0)
        results = snap.get("node_results") or []

        # 1. 同步基础 status
        for n in nodes:
            nid = str(n["id"])
            st = int(n.get("status", 0))
            if st == 2 and nid not in self.node_states:
                self.node_states[nid] = "done"
            elif st == 1 and self.node_states.get(nid) != "done":
                self.node_states[nid] = "running"
            elif st == 3:
                self.node_states[nid] = "failed"

        # 2. node_results 优先（更精确的执行结果）
        for r in results:
            nid = str(r.get("node_id", ""))
            if not nid:
                continue
            if r.get("success") is True:
                self.node_states[nid] = "done"
            elif r.get("success") is False:
                self.node_states[nid] = "failed"

        # 3. 当前执行节点标记为 running
        if 0 <= current_idx < len(nodes):
            cur_id = str(nodes[current_idx]["id"])
            if self.node_states.get(cur_id) not in ("done", "failed", "skipped"):
                self.node_states[cur_id] = "running"

    def get_latest(self) -> dict:
        """获取最新快照（注入实时 node_states）"""
        with self._lock:
            if not self.latest:
                return {}
            result = dict(self.latest)
            result["node_states"] = dict(self.node_states)
            return result

    def get_node_states(self) -> dict[str, str]:
        with self._lock:
            return dict(self.node_states)

    def set_node_state(self, node_id: str, state: str) -> None:
        with self._lock:
            self.node_states[node_id] = state

    def mark_finished(self, error: str | None = None) -> None:
        with self._lock:
            if not self.finished:
                self.finished = True
                self.error = error
                self._finished_at = time.time()  # ✅ 关键：记录完成时间戳

    def mark_cancelled(self) -> None:
        with self._lock:
            if not self.finished:
                self.cancelled = True
                self.finished = True
                self._finished_at = time.time()


# ══════════════════════════════════════════════════
#  2. 内存垃圾回收器 (全局单例)
# ══════════════════════════════════════════════════

class StreamStateCleaner:
    """
    TaskStreamState 内存垃圾回收器
    - 守护线程：主进程退出时自动停止
    - 惰性启动：首次注册任务时才启动线程
    - TTL 兜底：防止异常未标记 finished 的任务永久驻留
    """

    DEFAULT_TTL = 3600          # 默认存活时间 1h
    CLEAN_INTERVAL = 60         # 清理周期 60s
    FINISHED_RETENTION = 300    # 已完成任务额外保留 5min（供前端最后一次轮询）

    def __init__(self):
        self._states: dict[str, TaskStreamState] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running = False

    def register(self, thread_id: str, state: TaskStreamState) -> None:
        """注册一个新的流式任务状态"""
        with self._lock:
            self._states[thread_id] = state
        self._ensure_started()
        logger.debug("[Cleaner] 注册任务 %s (当前活跃: %d)",
                     thread_id, len(self._states))

    def unregister(self, thread_id: str) -> None:
        """主动移除（通常不需要手动调用，由守护线程自动清理）"""
        with self._lock:
            removed = self._states.pop(thread_id, None)
        if removed:
            logger.debug("[Cleaner] 主动移除任务 %s", thread_id)

    def get(self, thread_id: str) -> TaskStreamState | None:
        """安全获取状态对象"""
        with self._lock:
            return self._states.get(thread_id)

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._states)

    def _ensure_started(self) -> None:
        """惰性启动守护线程（双重检查锁）"""
        if self._running:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._cleanup_loop,
                name="stream-state-cleaner",
                daemon=True,  # 守护线程：主进程退出时自动终止
            )
            self._thread.start()
            logger.info("[Cleaner] 清理线程已启动 (interval=%ds, ttl=%ds)",
                        self.CLEAN_INTERVAL, self.DEFAULT_TTL)

    def _cleanup_loop(self) -> None:
        """后台清理循环"""
        while self._running:
            try:
                time.sleep(self.CLEAN_INTERVAL)
                self._do_cleanup()
            except Exception as e:
                logger.error("[Cleaner] 清理循环异常: %s", e, exc_info=True)

    def _do_cleanup(self) -> None:
        """执行一轮清理"""
        now = time.time()
        to_remove: list[str] = []

        # 在锁内只做轻量判断，避免长时间持锁
        with self._lock:
            for tid, state in self._states.items():
                should_remove = False

                if state.finished:
                    # 条件1: 已完成且超过保留期 (FINISHED_RETENTION)
                    if state._finished_at and (now - state._finished_at > self.FINISHED_RETENTION):
                        should_remove = True
                else:
                    # 条件2: 未完成但超过 TTL（防泄漏兜底）
                    if state.is_expired(now):
                        should_remove = True
                        logger.warning("[Cleaner] TTL 超时强制回收: %s (age=%.0fs)",
                                       tid, now - state._created_at)

                if should_remove:
                    to_remove.append(tid)

            # 批量移除
            for tid in to_remove:
                del self._states[tid]

        if to_remove:
            logger.info("[Cleaner] 本轮清理 %d 个任务 (剩余活跃: %d)",
                        len(to_remove), len(self._states))

    def stop(self) -> None:
        """手动停止清理器（用于测试或优雅关闭）"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("[Cleaner] 已停止")


# ══════════════════════════════════════════════════
#  3. 全局状态表 (统一由 Cleaner 管理)
# ══════════════════════════════════════════════════

# ✅ 全局唯一实例
state_cleaner = StreamStateCleaner()


def get_stream_state(thread_id: str) -> TaskStreamState | None:
    """获取指定任务的状态对象"""
    return state_cleaner.get(thread_id)


def get_node_states(thread_id: str) -> dict[str, str]:
    """获取指定任务的节点状态字典"""
    state = get_stream_state(thread_id)
    return state.get_node_states() if state else {}


# ══════════════════════════════════════════════════
#  4. 后台线程启动器 (核心业务逻辑)
# ══════════════════════════════════════════════════

def start_stream(
    thread_id: str,
    user_input: str,
    enable_refine: bool,
    run_task_stream_fn: Callable
) -> str:
    """启动后台流式任务，返回 thread_id。"""
    state = TaskStreamState(thread_id)
    state_cleaner.register(thread_id, state)  # ✅ 统一注册

    def _worker():
        try:
            logger.info("[StreamMgr] 后台线程启动 | thread=%s", thread_id)
            for snapshot in run_task_stream_fn(user_input, thread_id, enable_refine):
                if state.cancelled:
                    logger.info("[StreamMgr] 收到取消 | thread=%s", thread_id)
                    break

                state.push(snapshot)

                snap_type = snapshot.get("type", "")
                if snap_type in ("complete", "cancelled", "timeout", "error"):
                    err = snapshot.get("message") or snapshot.get("error")
                    state.mark_finished(error=err or None)
                    break
            else:
                state.mark_finished()

            logger.info("[StreamMgr] 后台线程结束 | thread=%s", thread_id)
        except Exception as e:
            logger.error("[StreamMgr] 后台线程异常 | thread=%s err=%s", thread_id, e)
            state.mark_finished(error=str(e))
        # ✅ 不再需要 _cleanup_after_delay，Cleaner 会自动处理

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return thread_id


def resume_stream(
    thread_id: str,
    user_action: str = "continue",
    modified_input: str | None = None,
    target_node_index: int | None = None,
    run_task_stream_fn: Callable | None = None,
) -> str:
    """从 LangGraph checkpoint 恢复历史任务并启动后台流式执行。"""
    existing = get_stream_state(thread_id)
    if existing and not existing.finished:
        logger.warning("[StreamMgr] resume_stream: 任务仍在运行中 %s", thread_id)
        return thread_id

    cp_state = get_thread_state(thread_id)
    if not cp_state:
        raise ValueError(f"未找到 thread_id={thread_id} 的 checkpoint，无法恢复")

    logger.info("[StreamMgr] resume_stream: thread=%s action=%s",
                thread_id, user_action)

    state = TaskStreamState(thread_id)
    state_cleaner.register(thread_id, state)  # ✅ 统一注册

    try:
        resume_graph(
            thread_id=thread_id,
            user_action=user_action,
            modified_input=modified_input,
            target_node_index=target_node_index,
        )
    except Exception as e:
        logger.error("[StreamMgr] resume_graph 失败: %s", e)
        state.mark_finished(error=str(e))
        return thread_id

    if run_task_stream_fn is None:
        from .agent import run_task_stream as run_task_stream_fn

    def _worker():
        try:
            logger.info("[StreamMgr] resume 后台线程启动 | thread=%s", thread_id)
            for snapshot in run_task_stream_fn(
                user_input="", thread_id=thread_id,
                enable_refine=False, resume=True,
            ):
                if state.cancelled:
                    break
                state.push(snapshot)

                snap_type = snapshot.get("type", "")
                if snap_type in ("complete", "cancelled", "timeout", "error"):
                    err = snapshot.get("message") or snapshot.get("error")
                    state.mark_finished(error=err or None)
                    break
            else:
                state.mark_finished()
        except Exception as e:
            logger.error(
                "[StreamMgr] resume 异常 | thread=%s err=%s", thread_id, e)
            state.mark_finished(error=str(e))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return thread_id


# ══════════════════════════════════════════════════
#  5. 任务与节点操作接口
# ══════════════════════════════════════════════════

def cancel_stream(thread_id: str) -> bool:
    """取消正在运行的流式任务"""
    state = get_stream_state(thread_id)
    if not state:
        logger.warning("[StreamMgr] 取消失败：任务不存在 %s", thread_id)
        return False

    state.mark_cancelled()
    try:
        cancel_task(thread_id)
    except Exception as e:
        logger.warning("[StreamMgr] agent.cancel_task 异常: %s", e)

    logger.info("[StreamMgr] 已取消 | thread=%s", thread_id)
    return True


def complete_node(thread_id: str, node_id: str) -> dict[str, Any]:
    """用户标记节点完成"""
    state = get_stream_state(thread_id)
    if not state:
        return {"success": False, "error": "任务不存在或已结束"}
    state.set_node_state(node_id, "done")
    return {"success": True, "node_states": state.get_node_states()}


def skip_node(thread_id: str, node_id: str, dag: dict) -> dict[str, Any]:
    """用户跳过节点，级联跳过下游"""
    state = get_stream_state(thread_id)
    if not state:
        return {"success": False, "error": "任务不存在或已结束"}

    edges = dag.get("edges") or []
    state.set_node_state(node_id, "skipped")

    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(str(e["from"]), []).append(str(e["to"]))

    queue = [node_id]
    visited = {node_id}
    skipped = [node_id]
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                state.set_node_state(nxt, "skipped")
                visited.add(nxt)
                skipped.append(nxt)
                queue.append(nxt)

    return {"success": True, "skipped": skipped, "node_states": state.get_node_states()}


def fail_node(thread_id: str, node_id: str, dag: dict) -> dict[str, Any]:
    """用户标记节点失败，级联跳过下游"""
    state = get_stream_state(thread_id)
    if not state:
        return {"success": False, "error": "任务不存在或已结束"}

    edges = dag.get("edges") or []
    state.set_node_state(node_id, "failed")

    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(str(e["from"]), []).append(str(e["to"]))

    queue = [node_id]
    visited = {node_id}
    affected = [node_id]
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, []):
            if nxt not in visited:
                state.set_node_state(nxt, "skipped")
                visited.add(nxt)
                affected.append(nxt)
                queue.append(nxt)

    return {"success": True, "affected": affected, "node_states": state.get_node_states()}


def get_ready_nodes(thread_id: str, dag: dict) -> list[str]:
    """获取所有可操作节点（前置已完成且自身未处理）"""
    state = get_stream_state(thread_id)
    if not state:
        return []

    node_states = state.get_node_states()
    edges = dag.get("edges") or []
    nodes = dag.get("nodes") or []

    ready = []
    for node in nodes:
        nid = str(node["id"])
        if node_states.get(nid) in ("done", "running", "failed", "skipped"):
            continue

        deps_ok = True
        for e in edges:
            if str(e["to"]) == nid and node_states.get(str(e["from"])) != "done":
                deps_ok = False
                break
        if deps_ok:
            ready.append(nid)
    return ready


# ══════════════════════════════════════════════════
#  6. 视图层辅助函数
# ══════════════════════════════════════════════════

def snapshot_to_elements(snapshot: dict) -> list:
    """从 snapshot 提取 elements（供 Dash Cytoscape 渲染）"""
    nodes = snapshot.get("nodes") or []
    edges = snapshot.get("edges") or []
    if not nodes:
        return []
    node_states = snapshot.get("node_states") or {}
    return dag_to_cytoscape(nodes, edges, node_states)


def get_status_text(snapshot: dict) -> str:
    """从 snapshot 提取状态文本（供前端状态栏展示）"""
    if not snapshot:
        return "等待中..."

    snap_type = snapshot.get("type", "")
    msg = snapshot.get("message", "")

    if snap_type == "start":
        return "🚀 任务已提交"
    if snap_type == "progress":
        elapsed = snapshot.get("elapsed", 0)
        return f"{msg} ({elapsed:.0f}s)" if msg and elapsed else (msg or "处理中...")
    if snap_type == "interrupt":
        return f"⏸️ {msg or '等待用户操作'}"
    if snap_type == "complete":
        return f"✅ {snapshot.get('status_text', '完成')}"
    if snap_type == "cancelled":
        return "⏹️ 已停止"
    if snap_type == "timeout":
        return f"⏰ {msg or '超时'}"
    if snap_type == "error":
        return f"❌ {msg or '错误'}"
    if snap_type == "resume":
        return f"🔄 正在恢复执行... {msg}"

    return snapshot.get("status_text", "处理中...")


# ══════════════════════════════════════════════════
#  7. 公开 API
# ══════════════════════════════════════════════════

__all__ = [
    "state_cleaner",
    "start_stream",
    "resume_stream",
    "cancel_stream",
    "get_stream_state",
    "get_node_states",
    "complete_node",
    "skip_node",
    "fail_node",
    "get_ready_nodes",
    "snapshot_to_elements",
    "get_status_text",
]
