"""
nodes.py — LangGraph 节点函数（修复版）
"""
from __future__ import annotations
from task_planner.core.graph.state import TaskState, UserAction
from task_planner.core.database import (
    create_task_with_plan,
    mark_task_running,
    mark_task_failed,
    update_node_status,
)
from task_planner.infrastructure.llm_client import (
    _call_llm,  # pyright: ignore[reportPrivateImportUsage]
    _extract_json as _parse_json,  # pyright: ignore[reportPrivateImportUsage]
    direct_chat,
    generate_plan,
    recognize_intent,
    refine_node,
)
from task_planner.infrastructure.logger_setup import get_logger, set_req_id
import re
import pytest
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypedDict
import json
from langchain_core.runnables import RunnableConfig
from task_planner.utils.context import cancel_event_var
# ✅ 改为
from task_planner.infrastructure.config import (
    LLM_NODE_MODEL,
    LLM_NODE_TIMEOUT,
    EXECUTE_NODE_PROMPT,
    SENSITIVE_PATTERNS_CONFIG,
    MAX_INPUT_LENGTH,
    USER_VISIBLE_NODE_FIELDS,
    SENSITIVE_PATTERNS,
)

logger = get_logger(__name__)
_SENSITIVE_PATTERNS = SENSITIVE_PATTERNS


class SafeNodeView(TypedDict, total=False):
    """面向前端的节点视图，所有字段均为可选（过滤后可能缺失）"""
    id: int
    name: str
    details: str
    status: str
    result: str


def sanitize_node_for_user(node: dict[str, Any]) -> SafeNodeView:
    """
    过滤掉仅用于内部执行的 debug/meta 字段（如 retry_policy、preconditions 等）。
    普通用户视图只保留 name、details、status、result 等可读字段。
    """
    return {k: v for k, v in node.items() if k in USER_VISIBLE_NODE_FIELDS}  # type: ignore[return-value]


def sanitize_nodes_for_user(nodes: list[dict[str, Any]]) -> list[SafeNodeView]:
    """批量过滤节点列表"""
    return [sanitize_node_for_user(n) for n in nodes]


# ══════════════════════════════════════════════════
#  输入清理
# ══════════════════════════════════════════════════


def _sanitize_input(text: str, *, audit_log: bool = True) -> str:
    original_hash = hashlib.sha256(
        text.encode()).hexdigest() if audit_log else None
    sanitized = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    if audit_log and sanitized != text:
        # 仅记录哈希 + 脱敏后文本，不存明文
        logger.info("[Audit] Input redacted | hash=%s | sanitized_len=%d",
                    original_hash, len(sanitized))
    return sanitized


@pytest.mark.parametrize("input_text,expected", [
    ("正常文本", "正常文本"),                           # 无变化
    ("key=sk-abc12345678901234567", "key=[REDACTED_API_KEY]"),  # API Key
    ("密码: MyP@ss123", "password=[REDACTED]"),         # 密码
    ("a" * 3000, "a" * 2000),                          # 截断
    ("手机号13800138000", "手机号[REDACTED_PHONE]"),     # 手机号
    ("", ""),                                          # 空字符串
])
def test_sanitize_input(input_text, expected):
    assert _sanitize_input(input_text) == expected
# ══════════════════════════════════════════════════
#  ✅ 统一工具：从 config 安全提取 cancel_event
# ══════════════════════════════════════════════════

# ✅ 修复：接受 config 参数（保持调用方不变，向前兼容）


def _get_cancel_event(config: RunnableConfig | None = None) -> threading.Event | None:
    """
    从 ContextVar 安全获取取消事件。

    config 参数保留仅为兼容调用方签名，实际不从 config 读取。
    """
    return cancel_event_var.get()
# ══════════════════════════════════════════════════
#  节点函数（全部添加 config 参数）
# ══════════════════════════════════════════════════


def intent_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """意图识别节点"""
    rid = set_req_id()
    logger.info("[Graph] intent_node (req=%s)", rid)

    user_input = _sanitize_input(state["user_input"])
    cancel_event = _get_cancel_event(config)  # ✅ 从 config 获取
    intent = recognize_intent(user_input, req_id=rid,
                              cancel_event=cancel_event)

    return {
        "user_input": user_input,
        "intent": intent,
        "needs_planning": intent.get("needs_planning", False),
        "steps": state.get("steps", []) + [f"意图识别: planning={intent.get('needs_planning')}"],
    }


def plan_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """规划节点"""
    rid = set_req_id()
    logger.info("[Graph] plan_node (req=%s)", rid)

    cancel_event = _get_cancel_event(config)
    plan = generate_plan(
        state["user_input"], state["intent"],
        req_id=rid, cancel_event=cancel_event,
    )

    # ✅ 新增：记录原始 plan 结构，便于排查
    logger.info("[Graph] plan_node raw plan keys: %s (req=%s)",
                list(plan.keys()) if isinstance(plan, dict) else type(plan).__name__, rid)

    nodes_raw = list(plan.get("nodes", []))
    edges_raw = list(plan.get("edges", []))

    # ✅ 新增：空计划保护 —— 绝不允许 0 节点流入下游
    if not nodes_raw:
        logger.error(
            "[Graph] plan_node 产出空计划! raw_plan=%s (req=%s)",
            str(plan)[:500], rid,
        )
        raise ValueError(
            f"规划失败：LLM 未返回有效节点。请检查 planner prompt 或模型输出格式。(req={rid})"
        )

    logger.info("[Graph] plan_node: %d nodes, %d edges (req=%s)",
                len(nodes_raw), len(edges_raw), rid)

    return {
        "plan": plan,
        "nodes": nodes_raw,
        "edges": edges_raw,
        "steps": state.get("steps", []) + [f"规划完成: {len(nodes_raw)}个节点, {len(edges_raw)}条边"],
    }


def refine_node_fn(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """节点细化（并发）"""
    rid = set_req_id()
    logger.info("[Graph] refine_node (req=%s)", rid)

    nodes_raw = state["nodes"]
    intent = state["intent"]
    cancel_event = _get_cancel_event(config)
    logger.info("[Graph] refine_node: cancel_event=%s", cancel_event)

    def _refine_one(n: dict[str, Any], req_id: str, ce: threading.Event | None) -> dict[str, Any]:
        if ce and ce.is_set():
            logger.info("[Graph] 节点%s细化跳过(已取消, req=%s)", n.get("id"), req_id)
            n["details"] = "⏹️ 用户取消"
            return n
        try:
            # ✅ 修复1: 补全缺失的右括号，修正缩进
            r = refine_node(
                n,
                state["user_input"],
                str(intent.get("category", "other")),
                req_id=req_id,
                cancel_event=ce,
            )
            n["name"] = r.get("name", n.get("name", ""))
            n["details"] = r.get("details", r.get("detail", ""))
            n["meta"] = r.get("meta", {})
        except (RuntimeError, TimeoutError) as e:
            logger.warning("[Graph] 节点%s细化失败: %s (req=%s)",
                           n.get("id"), e, req_id)
            n["details"] = f"细化失败: {e}"
        return n

    refined: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for idx, n in enumerate(nodes_raw):
            if cancel_event and cancel_event.is_set():
                logger.info("[Graph] refine 提前终止，已提交 %d/%d (req=%s)",
                            idx, len(nodes_raw), rid)
                break
            futures[pool.submit(_refine_one, dict(n), rid, cancel_event)] = idx
        results = [None] * len(nodes_raw)
        for f in as_completed(futures):
            orig_idx = futures[f]
            results[orig_idx] = f.result()

        # ✅ 兜底：未提交的节点标记为取消
        for i in range(len(results)):
            if results[i] is None:
                fallback = dict(nodes_raw[i])
                fallback["details"] = "⏹️ 用户取消(未提交)"
                results[i] = fallback

        refined = results

    return {
        "refined_nodes": refined,
        "nodes": refined,
        "steps": state.get("steps", []) + ["节点细化完成"],
    }


def save_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """入库节点"""
    rid = set_req_id()
    logger.info("[Graph] save_node (req=%s)", rid)

    task_obj, _ = create_task_with_plan(
        raw_query=state["user_input"],
        intent_info=state["intent"],
        plan_data={"nodes": state["nodes"], "edges": state["edges"]},
        req_id=rid,
    )
    task_id = str(task_obj.task_id)

    return {
        "task_id": task_id,
        "steps": state.get("steps", []) + [f"已入库: {task_id}"],
    }


def render_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """渲染流程图节点"""
    rid = set_req_id()
    logger.info("[Graph] render_node (req=%s)", rid)

    from task_planner.utils.flowchart_pro import flowchart_pro
    html = flowchart_pro.render_interactive(
        state["nodes"], state["edges"], state["task_id"], rid
    )

    return {
        "flowchart_html": html,
        "steps": state.get("steps", []) + ["流程图渲染完成"],
    }


def execute_node(state: TaskState, config: RunnableConfig) -> dict:
    """执行节点（interrupt 等待用户指令）"""
    rid = set_req_id()
    logger.info("[Graph] execute_node (req=%s)", rid)

    from langgraph.types import interrupt

    nodes = state["nodes"]
    idx = state.get("current_node_index", 0)

    if idx >= len(nodes):
        return {"user_action": None}

    node = nodes[idx]
    nid = node.get("id", idx)
    name = node.get("name", f"步骤{nid}")

    mark_task_running(state["task_id"])
    cancel_event = _get_cancel_event(config)
    success, detail = _execute_single_node(
        node, state["user_input"], state["intent"],
        cancel_event=cancel_event,
        req_id=rid,
    )
    # ✅ 执行完后、interrupt 前，再次检查取消信号
    if cancel_event and cancel_event.is_set():
        logger.info(
            "[Graph] execute_node: 执行期间收到取消信号，跳过 interrupt (req=%s)", rid)
        return {
            "cancel_requested": True,
            "status_text": "⏹️ 已取消",
            "steps": state.get("steps", []) + [f"节点{nid} ⏹️ 用户取消"],
        }

    status = 2 if success else 3
    update_node_status(state["task_id"], nid, status, details=detail)

    node_results = state.get("node_results", []) + [
        {"node_id": nid, "success": success, "detail": detail}
    ]

    icon = "✅" if success else "❌"
    steps = state.get("steps", []) + [f"节点{nid} {icon} {name}"]

    # ✅ 构建面向用户的 interrupt payload（过滤掉 meta/debug 字段）
    user_visible_node = sanitize_node_for_user(node)
    interrupt_payload = {
        "type": "node_complete",
        "node_id": nid,
        "node_name": name,
        "success": success,
        "detail": detail,
        "node_info": user_visible_node,  # ✅ 只传用户可见字段
        "next_index": idx + 1,
        "total_nodes": len(nodes),
    }
    feedback = interrupt(interrupt_payload)

    action = feedback.get("action", UserAction.CONTINUE)
    modified_input = feedback.get("user_input", None)

    updates: dict[str, Any] = {
        "current_node_index": idx + 1,
        "node_results": node_results,
        "steps": steps,
        "user_action": action,
    }

    if action == UserAction.MODIFY and modified_input:
        updates["user_input"] = _sanitize_input(modified_input)
        updates["current_node_index"] = 0
        updates["node_results"] = []
        updates["nodes"] = []
        updates["edges"] = []
        updates["refined_nodes"] = []

    return updates


def direct_answer_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    rid = set_req_id()
    logger.info("[Graph] direct_answer_node (req=%s)", rid)
    cancel_event = _get_cancel_event(config)
    answer = direct_chat(state["user_input"], rid, cancel_event=cancel_event)

    # ✅ 直接回答也入库，确保历史记录可查
    from task_planner.core.database import create_direct_answer_task
    try:
        create_direct_answer_task(
            raw_query=state["user_input"],
            intent_info=state.get("intent", {}),
            response=answer,
            req_id=rid,
        )
    except Exception as e:
        logger.warning("[Graph] 直接回答入库失败(不影响返回): %s", e)

    return {
        "direct_response": answer,
        "messages": [
            {"role": "user", "content": state["user_input"]},
            {"role": "assistant", "content": answer},
        ],
        "steps": state.get("steps", []) + ["直接回答完成"],
    }


def cancel_node(state: TaskState, config: RunnableConfig) -> dict[str, Any]:
    """取消分支"""
    logger.info("[Graph] cancel_node")
    if state.get("task_id"):
        try:
            mark_task_failed(state["task_id"], error="用户取消")
        except (RuntimeError, TimeoutError) as e:
            logger.warning(
                "[Graph] cancel_node: mark_task_failed failed (task_id=%s, error=%s)",
                state.get("task_id"), e, exc_info=True
            )
    return {
        "cancel_requested": True,
        "status_text": "⏹️ 已取消",
        "steps": state.get("steps", []) + ["任务已取消"],
    }


# ══════════════════════════════════════════════════
#  路由函数（无需 config）
# ══════════════════════════════════════════════════

def route_after_intent(state: TaskState) -> str:
    if state.get("cancel_requested"):
        return "cancel"
    if not state.get("needs_planning", True):
        return "direct_answer"
    return "plan"


def route_after_execute(state: TaskState) -> str:
    action = state.get("user_action")
    if action == UserAction.CANCEL:
        return "cancel"
    if action == UserAction.MODIFY:
        return "intent"
    if action == UserAction.RETRY_NODE:
        return "execute"
    idx = state.get("current_node_index", 0)
    if idx >= len(state.get("nodes", [])):
        return "finish"
    return "execute"


def route_after_render(state: TaskState) -> str:
    return "execute"


# ══════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════

def _execute_single_node(
    node: dict[str, Any],
    user_input: str,
    intent: dict[str, Any],
    cancel_event: threading.Event | None = None,
    req_id: str | None = None,  # ✅ 新增：接收外层 rid
) -> tuple[bool, str]:
    """执行单个节点"""
    # ✅ 优先使用外层传入的 rid，避免线程池内生成新 rid 导致日志断裂
    rid = req_id or set_req_id()
    nid = node.get("id", "?")
    name = str(node.get("name", f"步骤{nid}"))
    detail = str(node.get("detail", ""))
    meta: dict[str, Any] = dict(node.get("meta", {}) or {})
    category = str(intent.get("category", "other"))

    prompt = EXECUTE_NODE_PROMPT.safe_substitute(
        user_input=user_input,
        category=category,
        name=name,
        detail=detail,
        preconditions=json.dumps(
            meta.get('preconditions', []), ensure_ascii=False),
        postconditions=json.dumps(
            meta.get('postconditions', []), ensure_ascii=False),
    )

    try:
        raw = _call_llm(
            model=LLM_NODE_MODEL,
            prompt=prompt,
            enable_thinking=False,
            req_id=rid,
            timeout=LLM_NODE_TIMEOUT,
            cancel_event=cancel_event,
        )
        data = _parse_json(raw)
        success = bool(data.get("success", True))
        result = str(data.get("result", "节点已执行"))
        notes = str(data.get("notes", ""))
        full = f"{result} | 备注: {notes}" if notes else result
        logger.info("[Executor] 节点%s ✅ %s (req=%s)", nid, name, rid)
        return success, full
    except (RuntimeError, TimeoutError) as e:
        logger.warning("[Executor] 节点%s ❌ %s (req=%s)", nid, e, rid)
        return False, f"⚠️ 执行失败: {e}"
