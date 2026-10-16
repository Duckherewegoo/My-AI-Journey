"""
database.py — MongoDB 数据层（生产最终版，pyright 0 errors）
"""
import logging
import datetime as _dt
from datetime import timezone, datetime
import time
from typing import Any
import threading
from task_planner.infrastructure.config import MONGO_DB, MONGO_HOST, MONGO_PORT, TASK_STATUS
from task_planner.infrastructure.logger_setup import get_req_id

logger = logging.getLogger("task_planner.db")


_STATUS_NAMES: dict[int, str] = {}


def _status_name(code: int) -> str:
    global _STATUS_NAMES
    if not _STATUS_NAMES:
        _STATUS_NAMES = {v: k for k, v in TASK_STATUS.items()}
    return _STATUS_NAMES.get(code, f"?({code})")


# ── MongoEngine 连接（延迟初始化） ────────────────
_engine_ready: bool = False
Task: Any = None
Plan: Any = None


_db_lock = threading.Lock()


def init_db() -> None:
    """连接 MongoDB；缺包或连接失败时抛错"""
    global _engine_ready
    if _engine_ready:
        return
    with _db_lock:
        if _engine_ready:
            return
    try:
        from mongoengine import connect  # type: ignore
        connect(db=MONGO_DB, host=MONGO_HOST, port=MONGO_PORT)
        _engine_ready = True
        _ensure_models()
        logger.info(
            "✅ MongoDB 连接成功 (%s:%d/%s)",
            MONGO_HOST, MONGO_PORT, MONGO_DB,
        )
    except ImportError:
        logger.warning("⚠️ mongoengine 未安装，数据库功能不可用")
        raise
    except Exception as e:
        logger.error("❌ MongoDB 连接失败: %s", e)
        raise


def _ensure_models() -> None:
    """定义 MongoEngine 文档类并绑定到模块全局"""
    global Task, Plan
    if Task is not None:
        return

    from mongoengine import (  # type: ignore
        BooleanField,
        DateTimeField,
        DictField,
        Document,
        IntField,
        ListField,
        StringField,
    )

    class _Plan(Document):  # type: ignore
        meta = {"collection": "plans"}  # noqa: RUF012
        plan_id = StringField(required=True, unique=True)
        graph_title = StringField(default="未命名计划")
        description = StringField(default="")
        nodes = ListField(DictField())
        edges = ListField(DictField())
        valid = BooleanField(default=True)
        modified_count = IntField(default=0)
        created_at = DateTimeField(
            default=lambda: _dt.datetime.now(timezone.utc)
        )
        updated_at = DateTimeField(
            default=lambda: _dt.datetime.now(timezone.utc)
        )

        def touch(self) -> None:
            self.updated_at = _dt.datetime.now(timezone.utc)
            self.modified_count = int(self.modified_count or 0) + 1

    class _Task(Document):  # type: ignore
        meta = {"collection": "tasks"}  # noqa: RUF012
        task_id = StringField(required=True, unique=True)
        raw_query = StringField(default="")
        intent_info = DictField(default=dict)
        plan_id = StringField(default="")
        # ✅ 新增：存储直接回答的内容，使非规划类会话也能被历史记录检索
        direct_response = StringField(default="")
        status = IntField(default=0)
        valid = BooleanField(default=True)
        retry_count = IntField(default=0)
        max_retries = IntField(default=3)
        error_msg = StringField(default="")
        created_at = DateTimeField(
            default=lambda: _dt.datetime.now(timezone.utc)
        )
        updated_at = DateTimeField(
            default=lambda: _dt.datetime.now(timezone.utc)
        )

        def set_status(self, new_status: int, error: str = "") -> None:
            old = int(self.status or 0)
            self.status = new_status
            self.error_msg = error
            self.updated_at = _dt.datetime.now(timezone.utc)
            self.save()
            logger.info(
                "[DB] Task %s 状态: %s → %s%s",
                str(self.task_id),
                _status_name(old),
                _status_name(new_status),
                f" (err={error})" if error else "",
            )

        def can_retry(self) -> bool:
            return int(self.retry_count or 0) < int(self.max_retries or 3)

        def inc_retry(self) -> None:
            self.retry_count = int(self.retry_count or 0) + 1
            self.updated_at = _dt.datetime.now(timezone.utc)
            self.save()
            logger.warning(
                "[DB] Task %s 重试计数 → %d/%d",
                str(self.task_id),
                int(self.retry_count),
                int(self.max_retries or 3),
            )

    Plan = _Plan
    Task = _Task


# ── 校验 / 补全 plan 字段 ──────────────────────────────
def _validate_plan(data: dict[str, Any]) -> dict[str, Any]:
    nodes_raw: list[dict[str, Any]] = list(data.get("nodes", []) or [])
    edges_raw: list[dict[str, Any]] = list(data.get("edges", []) or [])

    clean_nodes: list[dict[str, Any]] = []

    def _safe_int(val: Any, default: int) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    for i, n in enumerate(nodes_raw, 1):
        clean_nodes.append({
            "id": _safe_int(n.get("id"), default=i),
            "name": str(n.get("name", f"步骤{i}")),
            "details": str(n.get("details", "") or n.get("detail", "")),
            "status": _safe_int(n.get("status"), default=0),
        })

    id_set: set[int] = {n["id"] for n in clean_nodes}
    clean_edges: list[dict[str, Any]] = []
    for e in edges_raw:
        f = _safe_int(e.get("from"), default=0)
        t = _safe_int(e.get("to"), default=0)
        if f in id_set and t in id_set and f != t:
            clean_edges.append({
                "from": f,
                "to": t,
                "label": str(e.get("label", "")),
            })
        else:
            logger.warning("[DB] 丢弃无效边: %s→%s", f, t)
            logger.debug(
                "[DB] Plan 清洗完成: nodes=%d(原始%d), edges=%d(原始%d, 丢弃%d)",
                len(clean_nodes), len(nodes_raw),
                len(clean_edges), len(edges_raw), len(
                    edges_raw) - len(clean_edges),
            )

    data["nodes"] = clean_nodes
    data["edges"] = clean_edges
    data.setdefault("task_name", "未命名计划")
    data.setdefault("description", "")
    return data


# ══════════════════════════════════════════════════
#  公开 API
# ══════════════════════════════════════════════════

def create_task_with_plan(
    raw_query: str,
    intent_info: dict[str, Any],
    plan_data: dict[str, Any],
    req_id: str = "",
    valid: bool = True,
) -> tuple[Any, Any]:
    """agent.py 调用的入口"""
    _ensure_models()
    rid = req_id or get_req_id()
    task_id = f"task_{int(time.time() * 1000)}"
    plan_id = f"plan_{task_id}"
    plan_data = _validate_plan(plan_data)

    plan = Plan(  # type: ignore
        plan_id=plan_id,
        graph_title=str(plan_data.get("task_name", "未命名计划")),
        description=str(plan_data.get("description", "")),
        nodes=list(plan_data.get("nodes", [])),
        edges=list(plan_data.get("edges", [])),
        valid=valid,
        modified_count=0,
    ).save()
    try:
        task = Task(  # type: ignore
            task_id=task_id,
            raw_query=raw_query,
            intent_info=intent_info,
            plan_id=plan_id,
            status=(
                TASK_STATUS["PENDING"]
                if valid
                else TASK_STATUS["FAILED"]
            ),
            valid=valid,
        ).save()
    except Exception as e:
        logger.error("[DB] Task 创建失败，回滚 Plan=%s: %s", plan_id, e)
        plan.delete()  # 简单补偿：删除已创建的 Plan
        raise
    logger.info(
        "[DB] ✅ 创建 Task=%s / Plan=%s (nodes=%d, edges=%d, req=%s)",
        task_id, plan_id, len(plan.nodes), len(plan.edges), rid,
    )
    return task, plan


def create_task_and_plan(
    raw_query: str,
    intent_info: dict[str, Any],
    plan_data: dict[str, Any],
    valid: bool = True,
) -> tuple[Any, Any]:
    """向后兼容别名"""
    return create_task_with_plan(
        raw_query, intent_info, plan_data, valid=valid
    )


# ✅ 新增：为直接回答类会话创建 Task 记录（无 Plan）
def create_direct_answer_task(
    raw_query: str,
    intent_info: dict[str, Any],
    response: str,
    req_id: str = "",
) -> Any:
    """
    为不需要规划的直接回答创建历史记录。
    不创建 Plan，仅创建 Task 记录，direct_response 字段存储回答内容。
    """
    _ensure_models()
    rid = req_id or get_req_id()
    task_id = f"task_{int(time.time() * 1000)}"

    task = Task(  # type: ignore
        task_id=task_id,
        raw_query=raw_query,
        intent_info=intent_info,
        plan_id="",  # 直接回答无 Plan
        direct_response=response,
        status=TASK_STATUS["SUCCESS"],
        valid=True,
    ).save()

    logger.info(
        "[DB] ✅ 创建直接回答 Task=%s (req=%s)",
        task_id, rid,
    )
    return task


def get_task(task_id: str) -> dict[str, Any] | None:
    """返回 task 字段字典"""
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if not task:
        return None
    return {
        "task_id": str(task.task_id),
        "raw_query": str(task.raw_query),
        "status": int(task.status or 0),
        "valid": bool(task.valid),
        "retry_count": int(task.retry_count or 0),
        "max_retries": int(task.max_retries or 3),
        "error_msg": str(task.error_msg),
        "intent_info": dict(task.intent_info or {}),
        "plan_id": str(task.plan_id),
        # ✅ 新增：返回直接回答内容和是否有规划
        "direct_response": str(getattr(task, "direct_response", "") or ""),
        "has_plan": bool(task.plan_id),
    }


def get_plan(plan_id: str) -> dict[str, Any] | None:
    """返回 plan 字段字典"""
    _ensure_models()
    plan = Plan.objects(plan_id=plan_id).first() if Plan else None
    if not plan:
        return None
    return {
        "plan_id": str(plan.plan_id),
        "graph_title": str(plan.graph_title),
        "description": str(plan.description),
        "nodes": list(plan.nodes or []),
        "edges": list(plan.edges or []),
        "valid": bool(plan.valid),
        "modified_count": int(plan.modified_count or 0),
    }


def load_task_with_plan(task_id: str) -> dict[str, Any] | None:
    """Task + Plan 一起拿（直接回答类会话也兼容返回）"""
    task_dict = get_task(task_id)
    if not task_dict:
        logger.warning("[DB] 任务不存在: %s", task_id)
        return None
    # ✅ 直接回答类会话无 Plan，直接返回 task 即可
    if not task_dict.get("has_plan"):
        return {"task": task_dict, "plan": None}
    plan_dict = get_plan(task_dict["plan_id"])
    if not plan_dict:
        logger.error("[DB] Plan 丢失: %s", task_dict["plan_id"])
        return None
    return {"task": task_dict, "plan": plan_dict}


def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    """
    ✅ 修复：统一返回所有任务（含直接回答类），不再按 needs_planning 过滤。
    增加 has_plan 字段，前端可据此区分展示样式。
    """
    _ensure_models()
    results: list[dict[str, Any]] = []
    if not Task:
        return results
    for t in Task.objects.order_by("-created_at").limit(limit):
        intent_info = t.intent_info or {}
        summary = intent_info.get("summary", "")
        title = summary or (t.raw_query or "")[:30]
        has_plan = bool(t.plan_id)
        # ✅ 直接回答类用 💬 前缀，规划类用 📋 前缀，便于前端区分
        prefix = "📋" if has_plan else "💬"
        results.append({
            "task_id": str(t.task_id),
            "title": f"{prefix} {title}",
            "status": int(t.status or 0),
            "valid": bool(t.valid),
            "retry": f"{int(t.retry_count or 0)}/{int(t.max_retries or 3)}",
            "has_plan": has_plan,
            "created": (
                t.created_at.strftime("%Y-%m-%d %H:%M")
                if t.created_at else ""
            ),
        })
    return results


def get_recent_tasks(
    limit: int = 50, rid_tag: str = "query",
) -> list[str]:
    """✅ 修复：统一返回所有任务摘要，不过滤直接回答类"""
    _ensure_models()
    results: list[str] = []
    if not Task:
        return results
    for t in Task.objects.order_by("-created_at").limit(limit):
        intent_info = t.intent_info or {}
        summary = intent_info.get("summary", "")
        title = summary or (t.raw_query or "")[:30]
        status_name = _status_name(int(t.status or 0))
        has_plan = bool(t.plan_id)
        prefix = "📋" if has_plan else "💬"
        results.append(f"[{status_name}] {prefix} {title} | {t.task_id}")
    logger.debug(
        "[DB] 查询最近任务 %d 条 (tag=%s)", len(results), rid_tag
    )
    return results


def update_node_status(
    task_id: str,
    node_id: int,
    new_status: int,
    details: str = "",
) -> bool:
    """更新节点状态，线程安全"""
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if not task:
        logger.warning("[DB] update_node_status: 任务不存在 %s", task_id)
        return False
    plan = Plan.objects(plan_id=task.plan_id).first() if Plan else None
    if not plan:
        logger.error("[DB] update_node_status: Plan 丢失 %s", task.plan_id)
        return False

    nodes = list(plan.nodes or [])
    changed = False
   # 替代当前的 Python 层循环修改
    Plan.objects(
        plan_id=task.plan_id,
        nodes__id=node_id
    ).update_one(
        set__nodes__S__status=new_status,
        set__nodes__S__details=details,
        set__nodes__S__updated_at=datetime.now(timezone.utc).isoformat(),
        set__modified_at=datetime.now(timezone.utc),
    )

    if changed:
        plan.nodes = nodes
        plan.touch()
        plan.save()
    return changed


def mark_task_success(task_id: str) -> None:
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    # 只允许从非终态转移到终态
    if task.status in (TASK_STATUS["SUCCESS"], TASK_STATUS["FAILED"]):
        logger.warning("任务已处于终态 %s，忽略用户切换状态", task.status)
        return
    if task:
        task.set_status(TASK_STATUS["SUCCESS"])


def mark_task_failed(task_id: str, error: str = "") -> None:
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if task:
        task.set_status(TASK_STATUS["FAILED"], error)


def mark_task_timeout(task_id: str) -> None:
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if task:  # ← 补上
        task.set_status(TASK_STATUS["TIMEOUT"], "超过总时限")


def mark_task_running(task_id: str) -> None:
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if task:
        task.set_status(TASK_STATUS["RUNNING"])


class DBManager:
    """数据库管理器，供 app.py 调用"""

    def get_recent_tasks(
        self, limit: int = 50, rid_tag: str = "query",
    ) -> list[str]:
        return get_recent_tasks(limit, rid_tag)

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        return list_tasks(limit)

# ══════════════════════════════════════════════════
#  删除功能（MongoDB 版）
# ══════════════════════════════════════════════════


def delete_task(task_id: str) -> bool:
    """删除单个任务（级联删除关联的 Plan）"""
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if not task:
        logger.warning("[DB] 删除失败，任务不存在: %s", task_id)
        return False

    # 级联删除关联的 Plan
    if task.plan_id:
        Plan.objects(plan_id=task.plan_id).delete()
        logger.info("[DB] 级联删除 Plan=%s", task.plan_id)

    # 删除任务本身
    task.delete()
    logger.info("[DB] 删除任务 %s", task_id)
    return True


def batch_delete_tasks(task_ids: list[str]) -> int:
    """批量删除任务，返回删除数量"""
    if not task_ids:
        return 0
    _ensure_models()

    # 收集所有关联的 plan_id
    plan_ids: list[str] = []
    for t in Task.objects(task_id__in=task_ids):
        if t.plan_id:
            plan_ids.append(t.plan_id)

    # 级联删除 Plans
    if plan_ids:
        Plan.objects(plan_id__in=plan_ids).delete()
        logger.info("[DB] 级联删除 %d 个 Plan", len(plan_ids))

    # 批量删除 Tasks
    result = Task.objects(task_id__in=task_ids).delete()
    deleted_count = result[0] if isinstance(result, tuple) else result
    logger.info("[DB] 批量删除 %d 个任务", deleted_count)
    return int(deleted_count)

# ══════════════════════════════════════════════════
#  节点重置（供前端 Dash 回调 + 后端共用）
# ══════════════════════════════════════════════════


def reset_node_status(task_id: str, node_id: int) -> bool:
    """
    将指定节点状态重置为 PENDING(0)，同时清除 error_msg。
    返回 True 表示成功，False 表示任务/Plan不存在或节点未找到。
    """
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if not task:
        logger.warning("[DB] reset_node_status: 任务不存在 %s", task_id)
        return False
    plan = Plan.objects(plan_id=task.plan_id).first() if Plan else None
    if not plan:
        logger.error("[DB] reset_node_status: Plan 丢失 %s", task.plan_id)
        return False

    nodes = list(plan.nodes or [])
    changed = False
    for n in nodes:
        if n.get("id") == node_id:
            old = n.get("status", 0)
            n["status"] = TASK_STATUS.get("PENDING", 0)
            n.pop("error_msg", None)       # 清除旧错误信息
            n.pop("updated_at", None)      # 清除更新时间戳
            changed = True
            logger.info(
                "[DB] 节点重置 %s#%d: %d→%d (PENDING)",
                task_id, node_id, old, TASK_STATUS.get("PENDING", 0),
            )
            break

    if changed:
        plan.nodes = nodes
        plan.touch()
        plan.save()
    else:
        logger.warning(
            "[DB] reset_node_status: 节点 #%d 未在 Plan %s 中找到",
            node_id, task.plan_id,
        )
    return changed


def get_node_status(task_id: str, node_id: int) -> int | None:
    """
    查询单个节点的当前状态码。
    返回 None 表示任务/Plan/节点不存在。
    """
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None
    if not task:
        return None
    plan = Plan.objects(plan_id=task.plan_id).first() if Plan else None
    if not plan:
        return None
    for n in (plan.nodes or []):
        if n.get("id") == node_id:
            return int(n.get("status", 0))
    return None


db_manager = DBManager()
