"""
llm_client.py — LLM 调用封装（生产最终版）
══════════════════════════════════════════════════
职责：
  ✅ 统一调用 DashScope Generation API（真实模型，零 Mock）
  ✅ 意图识别 → 任务规划 → 节点细化，三阶段全真实
  ✅ 超时控制（秒，不再 *1000）+ 指数退避重试
  ✅ 最终失败抛异常（不隐瞒错误）
  ✅ JSON 鲁棒提取（兼容 markdown 代码块 / 单引号 / 多余文本）
  ✅ 结构化异常：NetworkError / ModelError / ParseError / AuthError

设计原则：
  「不玩虚的」—— 主链路绝不返回伪造数据。
  如果 API Key 缺失 / 网络不通 / 模型不可用，直接报错让调用方决定怎么办。
  Mock 仅存在于 tests/mock_llm.py，主链路零感知。
"""
import time
import json
import re
import ast
import logging
from typing import Optional, Dict, Any, List

from .config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    USE_MOCK_LLM,
    LLM_INTENT_MODEL,
    LLM_PLANNER_MODEL,
    LLM_NODE_MODEL,
    LLM_INTENT_ENABLE_THINKING,
    LLM_PLANNER_ENABLE_THINKING,
    LLM_NODE_ENABLE_THINKING,
    LLM_THINKING_BUDGET,
    LLM_TIMEOUT,
    LLM_MAX_RETRIES,
    LLM_RETRY_BACKOFF,
    LLM_NODE_TIMEOUT,
    INTENT_PROMPT,
    PLANNER_PROMPT,
    NODE_REFINE_PROMPT,
)
from .logger_setup import get_logger, get_req_id

logger = get_logger("task_planner.llm")


# ═════════════════════════════════════════════════
#  自定义异常体系
# ═════════════════════════════════════════════════
class LLMError(Exception):
    """LLM 调用基类异常"""
    pass


class LLMAuthError(LLMError):
    """API Key 无效 / 过期 / 无权限"""
    pass


class LLMNetworkError(LLMError):
    """网络不通 / 超时 / 服务端 5xx"""
    pass


class LLMModelError(LLMError):
    """模型不存在 / 未开通 / 资源不足"""
    pass


class LLMParseError(LLMError):
    """API 返回了，但内容无法解析为合法 JSON"""
    pass


# ═════════════════════════════════════════════════
#  DashScope SDK 延迟加载
# ═════════════════════════════════════════════════
_sdk_ready = False
Generation = None  # type: ignore


def _ensure_sdk():
    """延迟加载 DashScope SDK，只在第一次真实调用时 import"""
    global _sdk_ready, Generation
    if _sdk_ready:
        return
    if not DASHSCOPE_API_KEY:
        raise LLMAuthError(
            "未配置 DASHSCOPE_API_KEY，请在 .env 中设置后重启服务"
        )
    try:
        from dashscope import Generation as _Gen  # type: ignore
        Generation = _Gen
        _sdk_ready = True
        logger.info("[LLMClient] DashScope SDK 加载成功")
        if DASHSCOPE_BASE_URL:
            logger.info("[LLMClient] 使用自定义 Base URL: %s", DASHSCOPE_BASE_URL)
    except ImportError:
        raise LLMError("dashscope 未安装，请执行: pip install dashscope")


# ═════════════════════════════════════════════════
#  工具函数
# ═════════════════════════════════════════════════
def _extract_json(raw: str) -> Dict[str, Any]:
    """
    从 LLM 输出中鲁棒地提取 JSON 字典。
    兼容：纯 JSON / ```json 代码块 / 前后有废话 / 单引号 JSON。
    失败抛 LLMParseError。
    """
    if not raw or not isinstance(raw, str):
        raise LLMParseError("LLM 返回为空或非字符串")

    text = raw.strip()

    # 1. 去掉 markdown 代码块包裹
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?\s*```$", "", text, flags=re.MULTILINE)

    # 2. 单引号 → 双引号（LLM 有时会输出 Python 风格）
    if text.startswith("{") and "'" in text:
        try:
            result = ast.literal_eval(text)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    # 3. 定位第一个 { 和最后一个 }
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMParseError(f"未找到 JSON 对象，原始内容前200字: {raw[:200]}")
    candidate = text[start:end + 1]

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"JSON 解析失败: {e}，内容前200字: {candidate[:200]}")

    if not isinstance(data, dict):
        raise LLMParseError(f"JSON 根类型不是 object，而是 {type(data).__name__}")
    return data


def _classify_error(exc: Exception) -> LLMError:
    """把底层异常归类到自定义异常体系"""
    msg = str(exc).lower()
    if any(k in msg for k in ("api key", "unauthorized", "invalidapikey", "forbidden", "认证")):
        return LLMAuthError(f"认证失败: {exc}")
    if any(k in msg for k in ("model", "not found", "not exist", "无权限", "未开通", "资源")):
        return LLMModelError(f"模型不可用: {exc}")
    if any(k in msg for k in ("timeout", "连接", "connection", "network", "503", "502", "504", "超时")):
        return LLMNetworkError(f"网络/服务异常: {exc}")
    return LLMError(f"LLM 调用失败: {exc}")


# ═════════════════════════════════════════════════
#  核心调用函数（真实模型，零 Mock）
# ═════════════════════════════════════════════════
def _call_dashscope(
    model: str,
    prompt: str,
    enable_thinking: bool,
    req_id: str,
    timeout: Optional[int] = None,
) -> str:
    """
    统一 DashScope 调用：Generation.call + 重试 + 超时。

    参数：
      model           : DashScope 模型名（如 qwen3.7-flash-2026-07-15）
      prompt          : 完整 prompt 字符串
      enable_thinking : 是否开启思考模式
      req_id          : 请求追踪 ID
      timeout         : 超时秒数（默认 LLM_TIMEOUT）

    返回：模型输出的纯文本字符串。
    任何失败都会抛自定义异常，绝不返回伪造内容。
    """
    _ensure_sdk()

    if timeout is None:
        timeout = LLM_TIMEOUT  # 秒

    last_error: Optional[LLMError] = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        t0 = time.time()
        try:
            logger.debug(
                "[LLMClient] 调用 %s (第%d次, timeout=%ds, req=%s)",
                model, attempt, timeout, req_id,
            )
            resp = Generation.call(  # type: ignore
                api_key=DASHSCOPE_API_KEY,
                base_url=DASHSCOPE_BASE_URL if DASHSCOPE_BASE_URL else None,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=False,
                result_format="message",
                enable_thinking=enable_thinking,
                thinking_budget=LLM_THINKING_BUDGET if enable_thinking else None,
                timeout=timeout,            # ✅ 秒，不再 *1000
            )
            elapsed_ms = int((time.time() - t0) * 1000)

            # HTTP 状态码
            if resp.status_code != 200:
                raise RuntimeError(
                    f"HTTP {resp.status_code}: {getattr(resp, 'message', '未知错误')}"
                )

            # 提取 content（Generation 返回纯字符串）
            output = resp.output
            if not output:
                raise RuntimeError("API 返回 output 为空")
            choices = output.choices if hasattr(output, "choices") else []
            if not choices:
                raise RuntimeError("API 返回空 choices")
            msg = choices[0].message if hasattr(choices[0], "message") else None
            content = getattr(msg, "content", "") if msg else ""

            # 字符串化兜底
            if not isinstance(content, str):
                content = str(content)
            content = content.strip()

            # thinking 模式下 content 可能为空，尝试 reasoning_content
            if not content and enable_thinking:
                reasoning = getattr(msg, "reasoning_content", "")
                if isinstance(reasoning, str) and reasoning.strip():
                    content = reasoning.strip()
                    logger.debug("[LLMClient] 使用 reasoning_content (req=%s)", req_id)

            if not content:
                raise RuntimeError("API 返回内容为空（content 与 reasoning 均为空）")

            logger.info(
                "[LLMClient] ✅ %s 调用成功 (%dms, attempt=%d, req=%s)",
                model, elapsed_ms, attempt, req_id,
            )
            return content

        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            last_error = _classify_error(e)
            wait = LLM_RETRY_BACKOFF ** attempt
            logger.warning(
                "[LLMClient] ⚠️ %s 失败 (%dms, attempt=%d/%d, wait=%ds, err=%s, req=%s)",
                model, elapsed_ms, attempt, LLM_MAX_RETRIES, wait, last_error, req_id,
            )
            # 认证错误 / 模型错误不重试（重试也没用）
            if isinstance(last_error, (LLMAuthError, LLMModelError)):
                logger.error("[LLMClient] 🔴 不可恢复错误，终止重试: %s", last_error)
                raise last_error
            if attempt < LLM_MAX_RETRIES:
                time.sleep(wait)

    # 全部重试耗尽
    logger.error(
        "[LLMClient] ❌ %s 最终失败 (req=%s): %s",
        model, req_id, last_error,
    )
    raise last_error or LLMError(f"{model} 调用最终失败")


# ═════════════════════════════════════════════════
#  公开接口 ①：意图识别
# ═════════════════════════════════════════════════
def recognize_intent(user_input: str) -> Dict[str, Any]:
    """
    识别用户意图，返回结构化 dict。
    主链路零 Mock：如果 LLM 不可用直接抛异常。
    """
    req_id = get_req_id()

    if not user_input or not user_input.strip():
        raise ValueError("用户输入为空")

    prompt = INTENT_PROMPT.format(user_input=user_input.strip())
    logger.info("[Intent] 🔍 开始意图识别 (input_len=%d, req=%s)", len(user_input), req_id)

    raw = _call_dashscope(
        model=LLM_INTENT_MODEL,
        prompt=prompt,
        enable_thinking=LLM_INTENT_ENABLE_THINKING,
        req_id=req_id,
    )

    intent = _extract_json(raw)

    # 字段校验 + 兜底
    if not isinstance(intent.get("needs_planning"), bool):
        raise LLMParseError(
            f"needs_planning 字段缺失或类型错误，原始: {raw[:200]}"
        )
    if intent["needs_planning"] is False and not intent.get("summary"):
        raise LLMParseError("无需规划时 summary 不能为空")

    valid_categories = {
        "cooking", "engineering", "logistics",
        "learning", "life_admin", "creative", "other",
    }
    if intent.get("category") not in valid_categories:
        logger.warning(
            "[Intent] category=%s 不在白名单，归为 other (req=%s)",
            intent.get("category"), req_id,
        )
        intent["category"] = "other"

    logger.info(
        "[Intent] ✅ 识别完成 | planning=%s category=%s req=%s",
        intent["needs_planning"], intent["category"], req_id,
    )
    return intent


# ═════════════════════════════════════════════════
#  公开接口 ②：任务规划
# ═════════════════════════════════════════════════
def generate_plan(user_input: str, intent_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    根据意图信息生成 DAG 任务计划。
    返回 {task_name, description, nodes, edges}。
    """
    req_id = get_req_id()
    category = intent_info.get("category", "other")
    summary = intent_info.get("summary", "")

    prompt = (
        PLANNER_PROMPT
        .replace("{user_input}", user_input.strip())
        .replace("{category}", category)
        .replace("{summary}", summary)
    )
    logger.info("[Planner] 🧠 开始任务规划 (category=%s, req=%s)", category, req_id)

    raw = _call_dashscope(
        model=LLM_PLANNER_MODEL,
        prompt=prompt,
        enable_thinking=LLM_PLANNER_ENABLE_THINKING,
        req_id=req_id,
    )

    data = _extract_json(raw)

    # 字段校验
    if not data.get("nodes") or not isinstance(data["nodes"], list):
        raise LLMParseError("plan 缺少 nodes 数组")
    if not data.get("edges") or not isinstance(data["edges"], list):
        raise LLMParseError("plan 缺少 edges 数组")

    # 补全 + 强校验
    data.setdefault("task_name", "未命名任务")
    data.setdefault("description", "")

    valid_ids: set = set()
    clean_nodes = []
    for i, n in enumerate(data["nodes"], 1):
        clean_nodes.append({
            "id": i,
            "name": str(n.get("name", f"步骤{i}"))[:40],
            "detail": str(n.get("detail", "")),
            "status": 0,
        })
        valid_ids.add(i)
    data["nodes"] = clean_nodes

    clean_edges = []
    for e in data["edges"]:
        f, t = int(e.get("from", 0)), int(e.get("to", 0))
        if f in valid_ids and t in valid_ids and f != t:
            clean_edges.append({
                "from": f,
                "to": t,
                "label": str(e.get("label", ""))[:30],
            })
        else:
            logger.warning("[Planner] 丢弃无效边: %s→%s (req=%s)", f, t, req_id)
    data["edges"] = clean_edges

    # 环检测
    try:
        import networkx as nx  # type: ignore
        g = nx.DiGraph()
        for n in data["nodes"]:
            g.add_node(n["id"])
        for e in data["edges"]:
            g.add_edge(e["from"], e["to"])
        if not nx.is_directed_acyclic_graph(g):
            raise LLMParseError("LLM 生成的图存在环，不是合法 DAG")
        logger.info("[Planner] ✅ DAG 校验通过 (req=%s)", req_id)
    except ImportError:
        logger.debug("[Planner] networkx 未安装，跳过环检测 (req=%s)", req_id)

    logger.info(
        "[Planner] ✅ 规划完成 (nodes=%d, edges=%d, req=%s)",
        len(data["nodes"]), len(data["edges"]), req_id,
    )
    return data


# ═════════════════════════════════════════════════
#  公开接口 ③：节点细化
# ═════════════════════════════════════════════════
def refine_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单个节点补充行动细节。
    返回 {name, detail, meta}。
    """
    req_id = get_req_id()
    user_input = node.get("_user_input", "")
    category = node.get("_category", "other")
    node_json = json.dumps(
        {k: v for k, v in node.items() if not k.startswith("_")},
        ensure_ascii=False,
    )

    prompt = (
        NODE_REFINE_PROMPT
        .replace("{node_json}", node_json)
        .replace("{user_input}", user_input)
        .replace("{category}", category)
    )
    logger.info("[Refine] 🔧 细化节点 #%s (req=%s)", node.get("id"), req_id)

    raw = _call_dashscope(
        model=LLM_NODE_MODEL,
        prompt=prompt,
        enable_thinking=LLM_NODE_ENABLE_THINKING,
        req_id=req_id,
    )

    refined = _extract_json(raw)

    # 合并回原节点
    node["name"] = str(refined.get("name", node.get("name", "")))[:40]
    node["detail"] = str(refined.get("detail", ""))
    meta = refined.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    node["meta"] = {
        "preconditions": list(meta.get("preconditions", []) or []),
        "postconditions": list(meta.get("postconditions", []) or []),
        "retry_policy": str(meta.get("retry_policy", "失败后重试最多3次")),
    }
    return node


def refine_all_nodes(
    nodes: List[Dict[str, Any]],
    user_input: str,
    category: str,
) -> List[Dict[str, Any]]:
    """
    批量细化所有节点。每个节点注入 user_input/category 上下文后调用 LLM。
    单个节点失败不影响其他节点（记录错误后继续）。
    """
    req_id = get_req_id()
    logger.info("[Refine] 🔧 开始批量细化 (%d 个节点, req=%s)", len(nodes), req_id)

    refined = []
    for node in nodes:
        node["_user_input"] = user_input
        node["_category"] = category
        try:
            node = refine_node(node)
        except LLMError as e:
            logger.error("[Refine] 节点 #%s 细化失败: %s (req=%s)", node.get("id"), e, req_id)
            node.setdefault("detail", f"⚠️ 细化失败: {e}")
        finally:
            node.pop("_user_input", None)
            node.pop("_category", None)
        refined.append(node)

    success_count = sum(1 for n in refined if n.get("detail") and "失败" not in str(n.get("detail", "")))
    logger.info("[Refine] ✅ 批量细化完成 (%d/%d 成功, req=%s)",
                success_count, len(refined), req_id)
    return refined


# ═════════════════════════════════════════════════
#  单例封装（供 agent.py 以面向对象方式调用）
# ═════════════════════════════════════════════════
class LLMClient:
    """LLM 客户端单例"""

    def recognize_intent(self, user_input: str) -> Dict[str, Any]:
        return recognize_intent(user_input)

    def generate_plan(self, user_input: str, intent_info: Dict[str, Any]) -> Dict[str, Any]:
        return generate_plan(user_input, intent_info)

    def refine_node(self, node: Dict[str, Any]) -> Dict[str, Any]:
        return refine_node(node)

    def refine_all_nodes(self, nodes, user_input, category) -> List[Dict[str, Any]]:
        return refine_all_nodes(nodes, user_input, category)


llm_client = LLMClient()
