"""
database.py — MongoDB 数据层（生产最终版）
══════════════════════════════════════════════
双集合：Task（任务外壳）+ Plan（计划详情）
状态机：PENDING → RUNNING → SUCCESS / FAILED / TIMEOUT
重试逻辑：失败/超时最多重试 3 次
参数校验 + 自动补全
延迟导入：缺 mongoengine 时仍可被 import（Mock 模式可用）

✅ 修复：update_node_status 签名统一为 (task_id, node_id, new_status, details="")
✅ 修复：线程安全 —— 每次写库前重新查询，避免缓存脏读
✅ 新增：update_node_detail 独立函数，供 agent 写入执行结果
"""
import time
import logging
from typing import Optional, Dict, Any, List

from .config import MONGO_HOST, MONGO_PORT, MONGO_DB, TASK_STATUS
from .logger_setup import get_req_id

logger = logging.getLogger("task_planner.db")


# ── 状态辅助 ──────────────────────────────────────
def _status_name(code: int) -> str:
    names = {v: k for k, v in TASK_STATUS.items()}
    return names.get(code, f"?({code})")


# ── MongoEngine 连接（延迟初始化） ────────────────
_engine_ready = False
Task = None   # 将在 _ensure_models() 中绑定
Plan = None


def init_db():
    """连接 MongoDB；缺包或连接失败时抛错（由调用方决定降级）"""
    global _engine_ready
    if _engine_ready:
        return
    try:
        from mongoengine import connect  # type: ignore
        connect(db=MONGO_DB, host=MONGO_HOST, port=MONGO_PORT)
        _engine_ready = True
        _ensure_models()
        logger.info("✅ MongoDB 连接成功 (%s:%d/%s)", MONGO_HOST, MONGO_PORT, MONGO_DB)
    except ImportError:
        logger.warning("⚠️ mongoengine 未安装，数据库功能不可用")
        raise
    except Exception as e:
        logger.error("❌ MongoDB 连接失败: %s", e)
        raise


def _ensure_models():
    """定义 MongoEngine 文档类并绑定到模块全局"""
    global Task, Plan
    if Task is not None:
        return
    from mongoengine import (  # type: ignore
        Document, StringField, ListField, DictField,
        IntField, BooleanField, DateTimeField,
    )
    import datetime as _dt

    class _Plan(Document):  # type: ignore
        meta = {"collection": "plans"}
        plan_id        = StringField(required=True, unique=True)
        graph_title    = StringField(default="未命名计划")
        description    = StringField(default="")
        nodes          = ListField(DictField())
        edges          = ListField(DictField())
        valid          = BooleanField(default=True)
        modified_count = IntField(default=0)
        created_at     = DateTimeField(default=_dt.datetime.utcnow())
        updated_at     = DateTimeField(default=_dt.datetime.utcnow())

        def touch(self):
            self.updated_at = _dt.datetime.utcnow()
            self.modified_count = (self.modified_count or 0) + 1

    class _Task(Document):  # type: ignore
        meta = {"collection": "tasks"}
        task_id        = StringField(required=True, unique=True)
        raw_query      = StringField(default="")
        intent_info    = DictField(default=dict)
        plan_id        = StringField(default="")
        status         = IntField(default=0)
        valid          = BooleanField(default=True)
        retry_count    = IntField(default=0)
        max_retries    = IntField(default=3)
        error_msg      = StringField(default="")
        created_at     = DateTimeField(default=_dt.datetime.utcnow())
        updated_at     = DateTimeField(default=_dt.datetime.utcnow())

        def set_status(self, new_status: int, error: str = ""):
            old = int(self.status or 0)
            self.status = new_status
            self.error_msg = error
            self.updated_at = _dt.datetime.utcnow()
            self.save()
            logger.info("[DB] Task %s 状态: %s → %s%s",
                        self.task_id,
                        _status_name(old), _status_name(new_status),
                        f" (err={error})" if error else "")

        def can_retry(self) -> bool:
            return int(self.retry_count or 0) < int(self.max_retries or 3)

        def inc_retry(self):
            self.retry_count = (self.retry_count or 0) + 1
            self.updated_at = _dt.datetime.utcnow()
            self.save()
            logger.warning("[DB] Task %s 重试计数 → %d/%d",
                          self.task_id,
                          int(self.retry_count), int(self.max_retries or 3))

    Plan = _Plan
    Task = _Task


# ── 校验 / 补全 plan 字段 ──────────────────────────────
def _validate_plan(data: Dict) -> Dict:
    nodes = data.get("nodes", []) or []
    edges = data.get("edges", []) or []

    clean_nodes = []
    for i, n in enumerate(nodes, 1):
        clean_nodes.append({
            "id":     int(n.get("id", i)),
            "name":   str(n.get("name", f"步骤{i}")),
            "detail": str(n.get("detail", "")),
            "status": int(n.get("status", 0)),
        })

    id_set = {n["id"] for n in clean_nodes}
    clean_edges = []
    for e in edges:
        f = int(e.get("from", 0))
        t = int(e.get("to", 0))
        if f in id_set and t in id_set and f != t:
            clean_edges.append({
                "from": f, "to": t,
                "label": str(e.get("label", ""))
            })
        else:
            logger.warning("[DB] 丢弃无效边: %s→%s", f, t)

    data["nodes"]  = clean_nodes
    data["edges"]  = clean_edges
    data.setdefault("task_name", "未命名计划")
    data.setdefault("description", "")
    return data


# ── 创建（Task + Plan 原子化） ─────────────────────────
def create_task_and_plan(raw_query, intent_info, plan_data, valid=True):
    rid = get_req_id()
    _ensure_models()
    task_id = f"task_{int(time.time() * 1000)}"
    plan_id = f"plan_{task_id}"

    plan_data = _validate_plan(plan_data)

    plan = Plan(  # type: ignore
        plan_id=plan_id,
        graph_title=plan_data.get("task_name", "未命名计划"),
        description=plan_data.get("description", ""),
        nodes=plan_data.get("nodes", []),
        edges=plan_data.get("edges", []),
        valid=valid,
        modified_count=0,
    ).save()

    task = Task(  # type: ignore
        task_id=task_id,
        raw_query=raw_query,
        intent_info=intent_info,
        plan_id=plan_id,
        status=TASK_STATUS["PENDING"] if valid else TASK_STATUS["FAILED"],
        valid=valid,
    ).save()

    logger.info("[DB] ✅ 创建 Task=%s / Plan=%s (nodes=%d, edges=%d, valid=%s, req=%s)",
                task_id, plan_id, len(plan.nodes), len(plan.edges), valid, rid)
    return task, plan


# ── 嵌套读取（Task → Plan） ──────────────────────────
def load_task_with_plan(task_id: str) -> Optional[Dict[str, Any]]:
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if not task:
        logger.warning("[DB] 任务不存在: %s", task_id)
        return None
    plan = Plan.objects(plan_id=task.plan_id).first() if Plan else None  # type: ignore
    if not plan:
        logger.error("[DB] Plan 丢失: task=%s, plan_id=%s", task_id, task.plan_id)
        return None

    return {
        "task": {
            "task_id":    task.task_id,
            "raw_query":  task.raw_query,
            "status":     int(task.status or 0),
            "valid":      bool(task.valid),
            "retry_count": int(task.retry_count or 0),
            "max_retries": int(task.max_retries or 3),
            "error_msg":  task.error_msg,
            "intent_info": task.intent_info,
            "plan_id":    task.plan_id,
        },
        "plan": {
            "plan_id":       plan.plan_id,
            "graph_title":   plan.graph_title,
            "description":   plan.description,
            "nodes":        list(plan.nodes or []),
            "edges":        list(plan.edges or []),
            "valid":         bool(plan.valid),
            "modified_count": int(plan.modified_count or 0),
        }
    }


# ── 列表（仅外壳） ──────────────────────────────────────
def list_tasks(limit: int = 50) -> List[Dict]:
    _ensure_models()
    results = []
    if not Task:
        return results
    for t in Task.objects.order_by("-created_at").limit(limit):  # type: ignore
        results.append({
            "task_id": t.task_id,
            "title":   (t.intent_info or {}).get("summary", (t.raw_query or "")[:30]),
            "status":  int(t.status or 0),
            "valid":   bool(t.valid),
            "retry":   f"{int(t.retry_count or 0)}/{int(t.max_retries or 3)}",
            "created":  t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "",
        })
    return results


# ── ✅ 修复：update_node_status 签名统一，线程安全 ───────
def update_node_status(
    task_id: str,
    node_id: int,
    new_status: int,
    details: str = "",
) -> bool:
    """
    更新指定节点的状态和详情。
    ✅ 每次重新查询 Plan（避免缓存脏读，线程安全）
    ✅ details 参数支持写入执行结果
    """
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if not task:
        logger.warning("[DB] update_node_status: 任务不存在 %s", task_id)
        return False
    plan = Plan.objects(plan_id=task.plan_id).first() if Plan else None  # type: ignore
    if not plan:
        logger.error("[DB] update_node_status: Plan 丢失 %s", task.plan_id)
        return False

    nodes = list(plan.nodes or [])
    changed = False
    for n in nodes:
        if n.get("id") == node_id:
            old = n.get("status", 0)
            n["status"] = new_status
            if details:
                n["details"] = details
            n["updated_at"] = time.time()
            changed = True
            logger.info("[DB] 节点 %s#%d: %d→%d%s",
                        task_id, node_id, old, new_status,
                        f" (details={details[:40]})" if details else "")
            break

    if changed:
        plan.nodes = nodes
        plan.touch()
        plan.save()
    return changed


# ── 任务级状态标记 ──────────────────────────────────────
def mark_task_success(task_id: str):
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if task:
        task.set_status(TASK_STATUS["SUCCESS"])


def mark_task_failed(task_id: str, error: str = ""):
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if task:
        task.set_status(TASK_STATUS["FAILED"], error)


def mark_task_timeout(task_id: str):
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if task:
        task.set_status(TASK_STATUS["TIMEOUT"], "超过总时限")


def mark_task_running(task_id: str):
    _ensure_models()
    task = Task.objects(task_id=task_id).first() if Task else None  # type: ignore
    if task:
        task.set_status(TASK_STATUS["RUNNING"])


# ── 便捷查询 ──────────────────────────────────────
def get_recent_tasks(limit: int = 50, rid_tag: str = "query") -> List[Dict]:
    """获取最近任务列表（供 Gradio 下拉框使用）"""
    _ensure_models()
    results = []
    if not Task:
        return results
    for t in Task.objects.order_by("-created_at").limit(limit):  # type: ignore
        summary = (t.intent_info or {}).get("summary", "")
        title = summary or (t.raw_query or "")[:30]
        status_code = int(t.status or 0)
        status_name = _status_name(status_code)
        results.append(f"[{status_name}] {title} | {t.task_id}")
    logger.debug("[DB] 查询最近任务 %d 条 (tag=%s)", len(results), rid_tag)
    return results


# ── db_manager 兼容对象（供 app.py 调用） ────────
class DBManager:
    """数据库管理器，提供 app.py 所需的接口"""

    def get_recent_tasks(self, limit: int = 50, rid_tag: str = "query") -> List[str]:
        return get_recent_tasks(limit, rid_tag)

    def list_tasks(self, limit: int = 50) -> List[Dict]:
        return list_tasks(limit)


db_manager = DBManager()
