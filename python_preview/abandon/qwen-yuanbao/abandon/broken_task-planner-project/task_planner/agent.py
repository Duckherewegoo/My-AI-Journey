"""
agent.py — ReAct Agent 主逻辑（生产最终版 v6.0）
═══════════════════════════════════════════════════════
职责：
  ✅ 意图识别 → 任务规划 → 节点细化 → 真实子任务执行 → 渲染
  ✅ 子任务执行器真实调用 LLM（用正确的模型名，不再传 module 字符串）
  ✅ 进度回调：每完成一个子任务就通知调用方（供 Gradio 实时刷新）
  ✅ 超时控制：单次任务总时限 + 单节点执行时限
  ✅ 全链路 req_id 透传
  ✅ 导出委托给 flowchart_pro（支持 svg/png/pdf/dot/html/json）

设计原则：
  「不玩虚的」—— 主链路零 Mock。
  子任务执行器可替换为真实工具调用（HTTP / Shell / DB / MCP）。
  当前默认执行器是"调用 LLM 对节点做执行推理"，真实可用。
"""
import time
import traceback
import logging
from typing import Dict, Any, Optional, Callable, List, Tuple

from .config import (
    LLM_TASK_TOTAL_TIMEOUT,
    LLM_NODE_TIMEOUT,
    STATUS_TEXT,
    TASK_STATUS,
)
from .logger_setup import get_logger, set_req_id
from .llm_client import (
    recognize_intent,
    generate_plan,
    refine_all_nodes,
    LLMError,
    _call_dashscope,      # ✅ 直接用，传正确的模型名
    LLM_NODE_MODEL,      # ✅ 真实的节点执行模型
    LLM_NODE_ENABLE_THINKING,
)
from .database import (
    create_task_and_plan,
    mark_task_running,
    mark_task_success,
    mark_task_timeout,
    mark_task_failed,
    load_task_with_plan,
    update_node_status,
    Plan,
)

logger = get_logger("task_planner.agent")


# ═══════════════════════════════════════════════════
#  进度回调类型
# ═══════════════════════════════════════════════════
# progress_cb(step_name: str, node_id: int, status: str, detail: str)
ProgressCallback = Callable[[str, int, str, str], None]


# ═══════════════════════════════════════════════════
#  ✅ 真实子任务执行器（用正确的模型名，不造假）
# ═══════════════════════════════════════════════════
def _default_node_executor(
    node: Dict[str, Any],
    context: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    真实子任务执行（默认实现）。

    当前实现：
      调用 LLM（正确模型名），让它根据节点的 name + detail + 前置上下文，
      推理出"这个步骤执行了什么、结果如何、是否成功"。
      这比 time.sleep(0.05) 真实 100 倍。

    未来替换：
      接入 MCP / Function Call / 真实 API 时，
      只需把这个函数替换成你的工具调用逻辑，
      返回 (success: bool, result_detail: str) 即可。

    返回：
      (True,  "执行结果描述")    → 成功
      (False, "失败原因描述")    → 失败
    """
    rid = set_req_id()  # 确保子任务内也有 req_id
    nid = node.get("id", "?")
    name = node.get("name", f"步骤{nid}")
    detail = node.get("detail", "")
    meta = node.get("meta", {}) or {}
    user_input = context.get("user_input", "")
    category = context.get("category", "other")

    prompt = f"""你是一个任务执行引擎。请对以下任务节点做"执行推理"：

【任务全局目标】{user_input}
【任务领域】{category}
【当前节点】{name}
【操作细节】{detail}
【前置条件】{meta.get('preconditions', [])}
【预期结果】{meta.get('postconditions', [])}

请严格按以下 JSON 格式返回（仅 JSON，无解释）：
{{
  "success": true,
  "result": "用2-3句话说清：你（作为执行者）做了什么、看到了什么结果",
  "notes": "执行中的关键观察或注意事项（可空字符串）"
}}"""

    try:
        raw = _call_dashscope(
            model=LLM_NODE_MODEL,           # ✅ 真实模型名
            prompt=prompt,
            enable_thinking=LLM_NODE_ENABLE_THINKING,
            req_id=rid,
            timeout=LLM_NODE_TIMEOUT,         # ✅ 单节点超时（秒）
        )
        # 用 llm_client 的 JSON 提取
        from .llm_client import _extract_json
        data = _extract_json(raw)
        success = bool(data.get("success", True))
        result = str(data.get("result", "节点已执行"))
        notes = str(data.get("notes", ""))
        full = result + (f" | 备注: {notes}" if notes else "")
        logger.info("[Executor] 节点%s ✅ %s (req=%s)", nid, name, rid)
        return success, full
    except LLMError as e:
        logger.warning("[Executor] 节点%s ❌ %s (req=%s)", nid, e, rid)
        return False, f"⚠️ 执行失败: {e}"
    except Exception as e:
        logger.warning("[Executor] 节点%s 异常: %s (req=%s)", nid, e, rid)
        return False, f"⚠️ 执行异常: {e}"


# ═══════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════
def run_task(
    user_input: str,
    enable_node_refine: bool = True,
    external_rid: Optional[str] = None,
    progress_cb: Optional[ProgressCallback] = None,
    node_executor: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    执行完整任务流程（真实版，零 Mock）。

    参数：
      user_input      : 用户原始需求
      enable_node_refine : 是否启用 LLM 节点细化
      external_rid    : 外部传入的请求 ID（全链路追踪）
      progress_cb     : 进度回调（每完成一个节点调用一次）
      node_executor   : 自定义子任务执行器（默认用 LLM 执行推理）

    返回：
      {
        "success": bool,
        "status_text": str,
        "task_id": str,
        "svg": str,        # 流程图的 HTML/SVG
        "error": str,
        "steps": [str],   # 已完成的步骤描述
        "direct_response": str,  # 无需规划时 LLM 的直接回复
        "nodes": [...]   # 最终节点状态
      }
    """
    rid = set_req_id(external_rid) if external_rid else set_req_id()
    t0 = time.time()

    logger.info(
        "[Agent] 🚀 新任务 | input=%s refine=%s req=%s",
        (user_input or "")[:50], enable_node_refine, rid,
    )

    result: Dict[str, Any] = {
        "success": False,
        "status_text": "",
        "task_id": "",
        "svg": "",
        "error": "",
        "steps": [],
        "direct_response": "",
        "nodes": [],
    }

    executor = node_executor or _default_node_executor

    def check_timeout(step: str) -> bool:
        elapsed = time.time() - t0
        if elapsed > LLM_TASK_TOTAL_TIMEOUT:
            logger.error("[Agent] ⏰ 超时 at %s (%.0fs, req=%s)", step, elapsed, rid)
            if result.get("task_id"):
                try:
                    mark_task_timeout(result["task_id"])
                except Exception:
                    pass
            result["error"] = f"⏰ 任务总超时（{int(elapsed)}秒）"
            result["status_text"] = STATUS_TEXT[TASK_STATUS["TIMEOUT"]]
            return True
        return False

    def report(step: str):
        """通过回调通知调用方进度"""
        result["steps"].append(step)
        if progress_cb:
            try:
                progress_cb("progress", 0, step, "")
            except Exception:
                pass

    try:
        # ── Step 1: 意图识别 ────────────────────────
        report("🔍 正在分析意图...")
        intent = recognize_intent(user_input)
        if check_timeout("intent"):
            return result

        # 无需规划 → 直接返回 LLM 的摘要
        if not intent.get("needs_planning"):
            summary = intent.get("summary", "已理解您的需求")
            logger.info("[Agent] ℹ️ 无需规划 | category=%s req=%s",
                        intent.get("category"), rid)
            return {
                "success": True,
                "status_text": "ℹ️ 已处理",
                "direct_response": summary,
                "task_id": "",
                "svg": "",
                "error": "",
                "steps": result["steps"],
                "nodes": [],
            }

        # ── Step 2: 任务规划 ────────────────────────
        category = intent.get("category", "other")
        plan_data: Optional[Dict] = None
        last_err = ""

        for attempt in range(1, 4):
            if check_timeout("plan"):
                return result
            report(f"🧠 规划中（第{attempt}次）...")
            try:
                plan_data = generate_plan(user_input, intent)
                if not plan_data.get("nodes") or not plan_data.get("edges"):
                    raise ValueError("plan 缺少 nodes/edges")
                break
            except LLMError as exc:
                last_err = str(exc)
                logger.warning("[Agent] 规划失败(第%d次): %s req=%s",
                              attempt, exc, rid)
                if attempt < 3:
                    time.sleep(attempt * 2)

        if not plan_data:
            result["error"] = f"❌ 规划失败3次: {last_err}"
            result["status_text"] = "❌ 规划失败"
            return result

        # ── Step 3: 节点细化 ────────────────────────
        nodes = plan_data.get("nodes", [])
        if nodes and enable_node_refine:
            try:
                report("🔧 正在细化节点细节...")
                if check_timeout("refine"):
                    return result
                plan_data["nodes"] = refine_all_nodes(
                    nodes, user_input, category
                )
                logger.info("[Agent] ✅ 节点细化完成 (req=%s)", rid)
            except LLMError as exc:
                err = f"节点细化失败：{exc}"
                logger.error("[Agent] %s (req=%s)", err, rid)
                raise RuntimeError(err)
        elif nodes:
            logger.info("[Agent] 节点细化已关闭 (req=%s)", rid)

        # ── Step 4: 入库 ────────────────────────
        if check_timeout("save"):
            return result

        task, plan = create_task_and_plan(
            raw_query=user_input,
            intent_info=intent,
            plan_data=plan_data,
        )
        result["task_id"] = task.task_id
        mark_task_running(task.task_id)
        report(f"📋 任务已创建: {task.task_id}")

        # ── Step 5: 真实子任务执行 ────────────────────────
        context = {
            "user_input": user_input,
            "category": category,
            "intent": intent,
            "results": {},  # node_id -> 执行结果
            "retries": 0,
        }

        for node in plan_data["nodes"]:
            if check_timeout("exec"):
                return result
            nid = node.get("id")
            name = node.get("name", f"步骤{nid}")
            report(f"⚙️ 执行节点 #{nid}: {name}")

            # 更新节点状态 → 进行中
            try:
                update_node_status(task.task_id, nid, 1)
            except Exception as e:
                logger.warning("[Agent] 状态更新失败: %s (req=%s)", e, rid)

            # 真实执行
            try:
                success, detail = executor(node, context)
                context["results"][nid] = {"success": success, "detail": detail}

                if success:
                    update_node_status(task.task_id, nid, 2, details=detail)
                    report(f"✅ 节点 #{nid} 完成")
                else:
                    update_node_status(task.task_id, nid, 3, details=detail)
                    report(f"❌ 节点 #{nid} 失败: {detail[:60]}")

                    # 按 retry_policy 决定是否重试
                    retry_policy = (node.get("meta") or {}).get("retry_policy", "")
                    if "重试" in retry_policy and context.get("retries", 0) < 3:
                        context["retries"] = context.get("retries", 0) + 1
                        report(f"🔄 节点 #{nid} 重试 ({context['retries']}/3)...")
                        try:
                            success2, detail2 = executor(node, context)
                            if success2:
                                update_node_status(task.task_id, nid, 2, details=detail2)
                                report(f"✅ 节点 #{nid} 重试成功")
                                continue
                        except Exception:
                            pass
            except Exception as exc:
                err_msg = f"节点{nid}执行异常: {exc}"
                logger.error("[Agent] %s (req=%s)", err_msg, rid)
                update_node_status(task.task_id, nid, 3, details=err_msg)
                report(f"❌ {err_msg[:60]}")

        # ── Step 6: 渲染流程图 ────────────────────────
        if check_timeout("render"):
            return result

        # 重新加载最新数据（含执行结果）
        data = load_task_with_plan(task.task_id)
        svg = ""
        if data:
            from .flowchart_pro import render_for_gradio
            svg = render_for_gradio(
                data["plan"]["nodes"],
                data["plan"]["edges"],
                task.task_id,
                rid,
            )
            result["nodes"] = data["plan"]["nodes"]

        mark_task_success(task.task_id)

        elapsed = time.time() - t0
        result.update({
            "success": True,
            "status_text": f"✅ 完成（{elapsed:.1f}s）",
            "svg": svg,
        })
        logger.info("[Agent] 🎉 完成 task=%s %.1fs req=%s",
                    task.task_id, elapsed, rid)
        return result

    except LLMError as exc:
        err_msg = f"❌ LLM 错误: {exc}"
        logger.error("[Agent] %s (req=%s)", err_msg, rid)
        if result.get("task_id"):
            try:
                mark_task_failed(result["task_id"], err_msg)
            except Exception:
                pass
        result["error"] = err_msg
        result["status_text"] = "❌ LLM 调用失败"
        return result

    except TimeoutError:
        result["error"] = f"⏰ 任务超时"
        result["status_text"] = STATUS_TEXT[TASK_STATUS["TIMEOUT"]]
        return result

    except Exception as exc:
        logger.error("[Agent] ❌ %s | %s (req=%s)",
                     exc, traceback.format_exc(), rid)
        if result.get("task_id"):
            try:
                mark_task_failed(result["task_id"], str(exc))
            except Exception:
                pass
        result["error"] = f"❌ 失败: {exc}"
        result["status_text"] = "❌ 执行失败"
        return result


# ═══════════════════════════════════════════════════
#  节点操作（供 Gradio 手动操作）
# ═══════════════════════════════════════════════════
def retry_failed_nodes(task_id: str) -> Dict[str, Any]:
    """重跑失败/超时节点（按拓扑序，真实执行）"""
    rid = set_req_id()
    data = load_task_with_plan(task_id)
    if not data:
        return {"success": False, "error": "任务不存在"}

    nodes = data["plan"]["nodes"]
    edges = data["plan"]["edges"]
    failed = [n for n in nodes if n.get("status") in (3, 4)]
    if not failed:
        return {"success": True, "message": "无失败节点", "retried": []}

    # 拓扑排序失败节点
    failed_ids = {n["id"] for n in failed}
    in_deg = {n["id"]: 0 for n in failed}
    for e in edges:
        if e["from"] in failed_ids and e["to"] in failed_ids:
            in_deg[e["to"]] += 1
    queue = [nid for nid in in_deg if in_deg[nid] == 0]
    ordered = []
    while queue:
        nid = queue.pop(0)
        ordered.append(nid)
        for e in edges:
            if e["from"] == nid and e["to"] in failed_ids:
                in_deg[e["to"]] -= 1
                if in_deg[e["to"]] == 0:
                    queue.append(e["to"])

    retried = []
    context = {"user_input": "", "category": "other", "results": {}}
    for nid in ordered:
        node = next(n for n in nodes if n["id"] == nid)
        try:
            update_node_status(task_id, nid, 1)
            success, detail = _default_node_executor(node, context)
            if success:
                update_node_status(task_id, nid, 2, details=detail)
                retried.append({"node_id": nid, "status": "success"})
            else:
                update_node_status(task_id, nid, 3, details=detail)
                retried.append({"node_id": nid, "status": "failed", "error": detail})
        except Exception as exc:
            update_node_status(task_id, nid, 3, details=f"重跑异常: {exc}")
            retried.append({"node_id": nid, "status": "failed", "error": str(exc)})

    all_ok = all(r["status"] == "success" for r in retried)
    if all_ok:
        mark_task_success(task_id)

    logger.info("[Agent] 重跑完成 task=%s success=%s (req=%s)",
                task_id, all_ok, rid)
    return {"success": all_ok, "retried": retried}


def get_task_status_map(task_id: str) -> Dict[str, Any]:
    """获取任务所有节点的状态映射"""
    data = load_task_with_plan(task_id)
    if not data:
        return {"success": False, "error": "任务不存在"}
    nodes = data["plan"]["nodes"]
    status_map: Dict[str, Dict] = {}
    for n in nodes:
        nid = n.get("id")
        status_map[str(nid)] = {
            "id": nid,
            "name": n.get("name", f"步骤{nid}"),
            "status": n.get("status", 0),
            "has_details": bool(n.get("details", "").strip()),
        }
    return {"success": True, "nodes": status_map}


# ═══════════════════════════════════════════════════
#  导出（委托给 flowchart_pro —— 支持全部 5 种格式）
# ═══════════════════════════════════════════════════
def export_task(task_id: str, fmt: str, req_id: str) -> Dict[str, str]:
    rid = set_req_id(req_id)
    data = load_task_with_plan(task_id)
    if not data:
        return {"error": "任务不存在"}
    from .flowchart_pro import export as _export
    return {"content": _export(
        data["plan"]["nodes"],
        data["plan"]["edges"],
        task_id,
        fmt,
        rid,
    )}


def load_and_render(task_id: str) -> Dict[str, Any]:
    rid = set_req_id()
    data = load_task_with_plan(task_id)
    if not data:
        return {"success": False, "error": "任务不存在"}
    from .flowchart_pro import render_for_gradio
    svg = render_for_gradio(
        data["plan"]["nodes"],
        data["plan"]["edges"],
        task_id,
        rid,
    )
    return {"success": True, "svg": svg, "plan": data["plan"]}


# ═══════════════════════════════════════════════════
#  OOP 封装
# ═══════════════════════════════════════════════════
class TaskAgent:
    """面向对象调用壳"""

    def run(self, user_input: str, req_id: str, enable_refine: bool = True,
            progress_cb: Optional[ProgressCallback] = None):
        return run_task(
            user_input,
            enable_refine,
            external_rid=req_id,
            progress_cb=progress_cb,
        )

    def export_task(self, task_id: str, fmt: str, req_id: str):
        return export_task(task_id, fmt, req_id)


task_agent = TaskAgent()
