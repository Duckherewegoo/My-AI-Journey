"""
llm_client.py — LLM 调用封装（OpenAI 兼容版）
"""
import json
import re
import time
from typing import Any
from openai import OpenAI
import threading

from task_planner.infrastructure.config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, INTENT_PROMPT,
    LLM_INTENT_ENABLE_THINKING, LLM_INTENT_MODEL, LLM_MAX_RETRIES,
    LLM_NODE_ENABLE_THINKING, LLM_NODE_MODEL, LLM_NODE_TIMEOUT,
    LLM_PLANNER_ENABLE_THINKING, LLM_PLANNER_MODEL, LLM_RETRY_BACKOFF,
    LLM_THINKING_BUDGET, LLM_TIMEOUT, NODE_REFINE_PROMPT, PLANNER_PROMPT,
    USE_MOCK_LLM, SKIP_PLANNING_PATTERNS, THINK_RE, VALID_INTENT_CATEGORIES,
    VALID_INTENT_COMPLEXITIES, MOCK_RESPONSE_PREFIX, UNREPLACED_PATTERN,
)
from task_planner.infrastructure.logger_setup import get_logger
_SKIP_PLANNING_PATTERNS = SKIP_PLANNING_PATTERNS
logger = get_logger(__name__)

# ══════════════════════════════════════════════════
#  客户端初始化
# ══════════════════════════════════════════════════
_client_lock = threading.Lock()
_client: OpenAI | None = None
_dashscope_available = False


def get_llm_client() -> OpenAI | None:
    """线程安全的懒加载客户端获取器"""
    global _client, _dashscope_available
    if _client is not None:
        return _client

    with _client_lock:
        # Double-Checked Locking: 防止多线程同时通过外层检查后重复创建
        if _client is not None:
            return _client

        if USE_MOCK_LLM or not DASHSCOPE_API_KEY:
            logger.info("[LLMClient] 启用 Mock 模式")
            return None

        try:
            base_url = DASHSCOPE_BASE_URL or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            _client = OpenAI(api_key=DASHSCOPE_API_KEY, base_url=base_url)
            _dashscope_available = True
            logger.info("[LLMClient] OpenAI 兼容客户端就绪 (base=%s)", base_url)
        except ImportError:
            logger.error("[LLMClient] openai 未安装: pip install openai")
            return None

    return _client

# ══════════════════════════════════════════════════
#  工具函数
# ══════════════════════════════════════════════════


# ✅ [Fix-2] 用字符串拼接构建正则，彻底避免 HTML 标签在复制/渲染/版本管理中被吞噬
#    运行时等价于 re.compile(r'</think>.*?', re.DOTALL)
_THINK_RE = THINK_RE


def _extract_tail_json(text: str) -> str | None:
    """
    从含纯文本思考过程的响应中提取尾部 JSON。
    使用锚点跳跃 + 引号状态机，避免 O(n) 盲扫和字符串内花括号误判。
    """
    if not text:
        return None

    # 1. 锚点定位：直接跳到最后一个 }，跳过整个思考过程的无效遍历
    search_end = len(text)
    while True:
        json_end = text.rfind('}', 0, search_end)
        if json_end == -1:
            return None

        # 2. 从锚点向前搜索匹配的 {，带引号状态感知
        brace_depth = 0
        in_string = False
        escape_next = False
        json_start = -1

        for i in range(json_end, -1, -1):
            ch = text[i]

            # 转义字符处理：\" 不应切换引号状态
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue

            # 引号状态切换（仅在非转义时生效）
            if ch == '"':
                in_string = not in_string
                continue

            # 字符串内的花括号不参与结构匹配
            if in_string:
                continue

            # 结构括号计数
            if ch == '}':
                brace_depth += 1
            elif ch == '{':
                brace_depth -= 1
                if brace_depth == 0:
                    json_start = i
                    break

        # 3. 验证提取结果
        if json_start != -1 and json_end > json_start:
            candidate = text[json_start:json_end + 1]
            try:
                json.loads(candidate)
                logger.debug("[LLM] 尾部JSON提取成功 (锚点跳跃), len=%d", len(candidate))
                return candidate
            except json.JSONDecodeError:
                # 4. 失败恢复：当前 } 不是有效 JSON 结尾，向前找下一个 } 重试
                logger.debug("[LLM] 尾部JSON候选验证失败，向前搜索下一个锚点")
                search_end = json_end  # rfind 下次搜索范围缩小
                continue
        else:
            # 括号不平衡，当前锚点无效，继续向前搜索
            search_end = json_end
            continue

    # 所有锚点均失败
    return None


def _clean_json_str(text: str) -> str:
    """更稳健的 JSON 提取：兼容 thinking 标签、纯文本思考、markdown 代码块"""
    if not text or not isinstance(text, str):
        return "{}"

    # 1. 基础清洗
    text = text.strip().lstrip('\ufeff')
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)

    # 2. 剥离 thinking 标签（标准 thinking 格式）
    #    ✅ [Fix-2] 使用预编译的 _THINK_RE + 回退保护
    _prev = text
    text = _THINK_RE.sub('', text).strip()
    if not text:
        text = _prev
        logger.warning("[LLM] _clean_json_str thinking标签剥离后文本为空，已回退")

    # 3. 剥离 Qwen 风格的纯文本思考过程(优化)
    #    特征：以"思考过程"开头，JSON 通常在最后且是独立的 {...} 块
    if text.startswith("思考过程") or text.startswith("思考："):
        logger.debug("[LLM] _clean_json_str 检测到纯文本思考前缀，启用尾部JSON提取")

        # ✅ 替换为锚点跳跃 + 状态感知的提取函数
        candidate = _extract_tail_json(text)
        if candidate is not None:
            return candidate

        # 如果提取失败，不中断流程，继续向下走 L4/L5 降级策略
        logger.warning("[LLM] _clean_json_str 尾部JSON提取失败，进入后续降级解析")

    # 4. 去除 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE).strip()

    # 5. 优先尝试直接解析
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError as e:
        logger.debug(
            "[LLM] _clean_json_str 直接解析失败: %s | text前100字符: %s", e, text[:100])

    # 6. 降级：找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError as e:
            logger.debug("[LLM] _clean_json_str 降级解析也失败: %s", e)

    logger.warning("[LLM] _clean_json_str 所有解析均失败 | 原始前300字符: %s", text[:300])
    return "{}"


def _extract_json(raw: str) -> dict:
    """从 LLM 原始返回中提取 JSON dict"""
    logger.debug("[LLM] _extract_json input (first 200 chars): %s", raw[:200])
    try:
        cleaned = _clean_json_str(raw)
        if not cleaned or cleaned == "{}":
            if raw.strip().startswith("{") and "needs_planning" in raw:
                logger.error(
                    "[LLMClient] _clean_json_str 丢失了有效JSON! raw前300字符: %s", raw[:300]
                )
            return {}
        result = json.loads(cleaned)
        if isinstance(result, dict):
            logger.debug("[LLM] _extract_json 成功, keys=%s",
                         list(result.keys()))
        else:
            logger.warning(
                "[LLM] _extract_json 返回值非dict: type=%s", type(result).__name__)
        return result if isinstance(result, dict) else {}
    except json.JSONDecodeError as e:
        logger.warning(
            "[LLMClient] JSON 解析失败: %s | 原始前200字符: %s", e, raw[:200])
        return {}
    except Exception as e:
        logger.error("[LLMClient] _extract_json 非预期异常: %s: %s | 原始前200字符: %s",
                     type(e).__name__, e, raw[:200])
        return {}


def _normalize_llm_output(raw: dict, expected_keys: list[str]) -> dict:
    """
    将 LLM 返回的不同格式归一化为统一 schema。
    兼容 {"success": true, "result": "..."} 和 {"name": "...", "detail": "..."} 两种格式。
    """
    # 0. 入口类型守卫：防止上游 JSON 解析出 list/str 导致后续 .keys() 崩溃
    if not isinstance(raw, dict):
        logger.error(
            "[LLM] _normalize_llm_output 输入非 dict, 已拦截: type=%s, value=%s",
            type(raw).__name__, str(raw)[:100]
        )
        return {}

    # P0: 如果已经是目标格式（符合契约），直接透传（快速路径）
    if all(k in raw for k in expected_keys):
        return raw

    # P1: 兼容 executor 的 success/result 包装
    if "result" in raw:
        result_val = raw["result"]
        if isinstance(result_val, str):
            normalized = {"content": result_val}
            if "notes" in raw:
                normalized["meta"] = {"notes": raw["notes"]}
            return normalized
        else:
            # 风险修复：result 存在但非字符串时，记录日志而非静默跳过
            logger.warning(
                "[LLM] _normalize_llm_output 'result' 字段非字符串, 跳过P1适配: type=%s",
                type(result_val).__name__
            )

    # P2: 兼容 refine 的 name/detail/meta 格式
    if "detail" in raw:
        meta = raw.get("meta", {})
        # 风险修复：防止 LLM 返回 "meta": "some string" 导致下游操作 meta 时报 TypeError
        if not isinstance(meta, dict):
            logger.warning(
                "[LLM] _normalize_llm_output 'meta' 字段非 dict, 已重置为空字典: type=%s",
                type(meta).__name__
            )
            meta = {}
        return {"content": raw["detail"], "meta": meta}

    # P3: 兜底透传
    logger.warning(
        "[LLM] _normalize_llm_output 无法识别的输出格式: keys=%s", list(raw.keys())
    )
    return raw

# ══════════════════════════════════════════════════
#  核心调用
# ══════════════════════════════════════════════════


def _call_llm(
    model: str,
    prompt: str,
    enable_thinking: bool,
    req_id: str,
    timeout: float | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """
    统一 LLM 调用入口。

    - cancel_event 由上层通过参数显式传入（不再依赖 config 或常量 Key）
    - 当 enable_thinking=True 且 cancel_event 存在时，自动降级为流式调用
      以支持思考过程中的实时取消
    """
    if not _dashscope_available or not _client:
        raise RuntimeError("LLM 客户端未初始化，请检查 API Key")

    if timeout is None:
        timeout = LLM_NODE_TIMEOUT if enable_thinking else LLM_TIMEOUT

    last_error: Exception | None = None

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        if cancel_event and cancel_event.is_set():
            raise RuntimeError("任务已取消，停止 LLM 调用")

        t0 = time.time()
        try:
            logger.debug(
                "[LLMClient] 调用模型 %s (第%d次, timeout=%ss, thinking=%s, req=%s)",
                model, attempt, timeout, enable_thinking, req_id,
            )

            # 构建 extra_body，非 thinking 模式时直接传 None 避免冗余
            extra_body: dict[str, Any] | None = None
            if enable_thinking:
                extra_body = {
                    "enable_thinking": True,
                    "thinking_budget": LLM_THINKING_BUDGET,
                }

            content = ""

            # ✅ Thinking + Cancel → 流式调用，支持实时中断
            if enable_thinking and cancel_event is not None:
                stream = _client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    extra_body=extra_body,
                    timeout=timeout,
                )
                reasoning_chunks: list[str] = []
                content_chunks: list[str] = []
                try:
                    for chunk in stream:
                        if cancel_event.is_set():
                            stream.close()
                            raise RuntimeError("任务已取消，停止 LLM 流式读取")
                        if not chunk.choices:
                            continue

                        delta = chunk.choices[0].delta
                        # 分别收集思考内容和正文内容，防止丢失和顺序错乱
                        r = getattr(delta, "reasoning_content", None)
                        c = getattr(delta, "content", None)
                        if r:
                            reasoning_chunks.append(r)
                        if c:
                            content_chunks.append(c)
                finally:
                    try:
                        stream.close()
                    except Exception as close_err:
                        logger.debug(
                            "[LLMClient] stream.close() 异常(通常无害): %s", close_err
                        )

                # 思考内容在前，正文在后，符合自然阅读顺序和下游清洗预期
                content = ("".join(reasoning_chunks) +
                           "".join(content_chunks)).strip()

            else:
                # 非 Thinking 或无 cancel_event → 非流式调用
                response = _client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    extra_body=extra_body,
                    timeout=timeout,
                )
                msg = response.choices[0].message

                # 统一提取 content 和 reasoning，与流式分支行为保持一致
                text = getattr(msg, "content", None) or ""
                reasoning = getattr(msg, "reasoning_content", None) or ""

                if enable_thinking:
                    # Thinking 模式：拼接 reasoning + content，防止 reasoning 被静默丢弃
                    content = (reasoning + text).strip()
                else:
                    content = text.strip()

            if not content:
                raise RuntimeError("API 返回内容为空")

            elapsed_ms = int((time.time() - t0) * 1000)
            logger.info(
                "[LLMClient] ✅ %s 成功 (%dms, attempt=%d, thinking=%s, req=%s)",
                model, elapsed_ms, attempt, enable_thinking, req_id,
            )
            return content

        except RuntimeError as e:
            # 取消信号触发的 RuntimeError 不重试，直接向上抛出
            if "取消" in str(e):
                raise
            last_error = e
        except Exception as e:
            last_error = e

        elapsed_ms = int((time.time() - t0) * 1000)
        wait = LLM_RETRY_BACKOFF ** attempt
        logger.warning(
            "[LLMClient] ⚠️ %s 失败 (%dms, attempt=%d/%d, wait=%ds, err=%s, req=%s)",
            model, elapsed_ms, attempt, LLM_MAX_RETRIES, wait, last_error, req_id,
        )

        if attempt < LLM_MAX_RETRIES:
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("任务已取消，停止重试") from last_error
            time.sleep(wait)
        else:
            logger.error(
                "[LLMClient] ❌ %s 最终失败: %s (req=%s)", model, last_error, req_id
            )
            raise RuntimeError(f"LLM 调用最终失败: {last_error}") from last_error

    # 理论上不会到达这里，但满足类型检查器的返回值要求
    raise RuntimeError(f"LLM 调用最终失败: {last_error}")


# ══════════════════════════════════════════════════
#  模板渲染
# ══════════════════════════════════════════════════
_UNREPLACED_PATTERN = UNREPLACED_PATTERN


def _render_template(template, req_id: str, **kwargs) -> str:
    """
    安全渲染 string.Template。

    ✅ 使用 safe_substitute 替代 substitute：
       - substitute 是严格模式：模板中有多余 $ 或用户输入含 $ 时会抛 ValueError
       - safe_substitute 对未匹配的占位符保留原样，不会崩溃

    ✅ 渲染后记录 prompt 尾部日志，快速发现占位符未替换问题。
    ✅ 正则同时覆盖 ${var} 和 $var 两种格式，并排除 $$ 转义。
    """
    try:
        result = template.safe_substitute(**kwargs)
        # 记录尾部 150 字符，足以看到 <user_input> 区域是否被正确替换
        tail = result[-150:].replace('\n', '\\n')
        logger.debug(
            "[LLM] _render_template 渲染完成 (req=%s) | 尾部: %s", req_id, tail)

        # ✅ 主动检测：如果渲染后仍包含未替换的占位符，发出警告
        #    findall 返回元组列表如 [('var1', ''), ('', 'var2')]，展平并过滤空串
        matches = _UNREPLACED_PATTERN.findall(result)
        unreplaced = [name for group in matches for name in group if name]
        if unreplaced:
            logger.warning(
                "[LLM] _render_template 存在未替换占位符: %s (req=%s) "
                "请检查 config.py 中模板的占位符名是否与 kwargs 匹配",
                unreplaced, req_id,
            )
        return result
    except Exception as e:
        logger.error("[LLM] _render_template 渲染失败 (req=%s): %s", req_id, e)
        raise


# ══════════════════════════════════════════════════
#  公开接口
# ══════════════════════════════════════════════════


def direct_chat(
    user_input: str,
    req_id: str,
    cancel_event: threading.Event | None = None,
    timeout: float | None = None,
) -> str:
    """
    直接对话接口，不启用 Thinking，适用于简单问答和意图识别。

    ✅ 增加 timeout 参数透传，允许调用方按需覆盖默认超时。
    ✅ Mock 回复增加 MOCK_RESPONSE_PREFIX 前缀，便于下游识别跳过。
    """
    if USE_MOCK_LLM:
        return f"{MOCK_RESPONSE_PREFIX}{user_input}"
    return _call_llm(
        model=LLM_INTENT_MODEL,
        prompt=user_input,
        enable_thinking=False,
        req_id=req_id,
        cancel_event=cancel_event,
        timeout=timeout,
    )


def _validate_intent(intent: dict, user_input: str) -> dict:
    """
    ✅ 仅做枚举校验和非法值降级。
       不设置任何默认值——默认值统一由 recognize_intent 在 _validate_intent 之后处理。
       职责分离：本函数只管"纠偏"，不管"兜底"。

    ✅ 返回字典副本（浅拷贝），避免原地修改入参带来的副作用，
       保证上游仍可访问原始 LLM 返回值用于审计或重试判断。
    """
    validated = dict(intent)  # 浅拷贝，值是字符串，无需深拷贝

    if validated.get("category") not in VALID_INTENT_CATEGORIES:
        logger.warning(
            "[Intent] 非法 category=%s, 降级为 other",
            validated.get("category"),
        )
        validated["category"] = "other"

    if validated.get("complexity") not in VALID_INTENT_COMPLEXITIES:
        logger.warning(
            "[Intent] 非法 complexity=%s, 降级为 medium",
            validated.get("complexity"),
        )
        validated["complexity"] = "medium"

    # ✅ 不在此处设置任何默认值（如 needs_planning、summary 等）
    #    默认值统一在 recognize_intent 中处理
    return validated


def recognize_intent(
    user_input: str,
    req_id: str,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """
    意图识别主入口。
    采用 Pre-check → LLM → Validate → Default → Post-check 五层防御结构。
    """
    # ── Layer 0: 空输入短路 ──────────────────────────
    if not user_input or not user_input.strip():
        return {
            "needs_planning": False,
            "category": "other",
            "summary": "用户输入为空",
            "complexity": "simple",
        }

    # ── Layer 1: Pre-check 正则硬拦截 ────────────────
    for pattern in _SKIP_PLANNING_PATTERNS:
        if pattern.search(user_input):
            logger.info(
                "[Intent] 显式拒绝规划命中 (req=%s): %s",
                req_id, pattern.pattern,
            )
            return {
                "needs_planning": False,
                "category": "consultation",
                "summary": "用户显式拒绝规划",
                "complexity": "simple",
            }

    # ── Layer 2: Mock 短路（含取消感知）──────────────
    if USE_MOCK_LLM:
        # ✅ [Fix] Mock 路径也检查取消事件，保证测试中取消逻辑可验证
        if cancel_event and cancel_event.is_set():
            raise TimeoutError("Mock: cancelled by event")
        return _mock_intent(req_id)

    # ── Layer 3: LLM 调用 + 解析 ────────────────────
    try:
        prompt = _render_template(INTENT_PROMPT, req_id, user_input=user_input)

        raw = _call_llm(
            model=LLM_INTENT_MODEL,
            prompt=prompt,
            enable_thinking=LLM_INTENT_ENABLE_THINKING,
            req_id=req_id,
            cancel_event=cancel_event,
        )
        intent = _extract_json(raw)
        if not intent or not isinstance(intent, dict):
            raise ValueError("JSON解析为空或非dict")

        # ── Layer 4a: 枚举纠偏（只纠偏，不兜底）──────
        intent = _validate_intent(intent, user_input)

        # ── Layer 4b: 缺失字段兜底 ──────────────────
        intent.setdefault("needs_planning", False)
        intent.setdefault("category", "other")
        intent.setdefault("summary", "任务解析完成")
        intent.setdefault("complexity", "simple")

        # ── Layer 5: Post-check 二次拦截 ────────────
        if intent.get("needs_planning") is True:
            for pattern in _SKIP_PLANNING_PATTERNS:
                if pattern.search(user_input):
                    logger.warning(
                        "[Intent] LLM 误判 planning=True，正则二次拦截生效 (req=%s)",
                        req_id,
                    )
                    intent["needs_planning"] = False
                    intent["category"] = "consultation"
                    intent["summary"] = "用户显式拒绝规划(LLM纠偏)"
                    break

            # ✅ [核心改动] Post-check 修改了 category 后，
            #    重新走一次纠偏，确保 "consultation" 在白名单内
            #    （前提是 VALID_INTENT_CATEGORIES 已包含 "consultation"）
            intent = _validate_intent(intent, user_input)

        return intent

    # ── 异常兜底（细分错误类型）──────────────────────
    except TimeoutError:
        logger.error("[LLMClient] 意图识别超时 (req=%s)", req_id)
        summary = "意图识别超时"
    except ValueError as e:
        logger.error("[LLMClient] 意图解析格式错误: %s (req=%s)", e, req_id)
        summary = "意图解析格式错误"
    except RuntimeError as e:
        logger.error("[LLMClient] 意图识别服务异常: %s (req=%s)", e, req_id)
        summary = "意图识别服务异常"
    except Exception as e:
        # 兜底中的兜底：未预期的异常类型
        logger.exception("[LLMClient] 意图识别未知异常: %s (req=%s)", e, req_id)
        summary = "意图识别异常"

    return {
        "needs_planning": False,
        "category": "other",
        "summary": summary,
        "complexity": "simple",
    }


def generate_plan(
    user_input: str,
    intent_info: dict[str, Any],
    req_id: str,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """根据用户输入和意图信息生成执行计划（图结构：nodes + edges）。"""

    # ✅ 与 _mock_plan 对齐的真实字段契约
    _PLAN_REQUIRED_KEYS = ("task_name", "description", "nodes", "edges")

    if not isinstance(intent_info, dict):
        logger.error("[Planner] intent_info 类型非法: %s (req=%s)",
                     type(intent_info).__name__, req_id)
        return {
            "task_name": "规划失败",
            "description": "intent_info 参数类型非法",
            "nodes": [],
            "edges": [],
        }

    if USE_MOCK_LLM:
        if cancel_event and cancel_event.is_set():
            raise TimeoutError("Mock: cancelled by event")
        return _mock_plan(req_id)

    try:
        prompt = _render_template(
            PLANNER_PROMPT, req_id,
            user_input=user_input,
            category=intent_info.get("category", "other"),
            summary=intent_info.get("summary", ""),
        )
        raw = _call_llm(
            model=LLM_PLANNER_MODEL, prompt=prompt,
            enable_thinking=LLM_PLANNER_ENABLE_THINKING,
            req_id=req_id, cancel_event=cancel_event,
        )
        plan = _extract_json(raw)
        if not plan or not isinstance(plan, dict):
            raise ValueError("Plan JSON解析为空或非dict")

        # ✅ 按真实契约补全字段
        plan.setdefault("task_name", "未命名任务")
        plan.setdefault("description", "")
        plan.setdefault("nodes", [])
        plan.setdefault("edges", [])
        return plan

    except TimeoutError:
        logger.error("[Planner] 规划生成超时 (req=%s)", req_id)
        error_msg = "规划生成超时"
    except ValueError as e:
        logger.error("[Planner] 规划解析格式错误: %s (req=%s)", e, req_id)
        error_msg = f"规划解析格式错误: {e}"
    except RuntimeError as e:
        logger.error("[Planner] 规划生成服务异常: %s (req=%s)", e, req_id)
        error_msg = f"规划生成服务异常: {e}"
    except Exception as e:
        logger.exception("[Planner] 规划生成未知异常: %s (req=%s)", e, req_id)
        error_msg = "规划生成异常"

    # ✅ 失败时也返回合法图结构，description 中携带错误信息
    return {
        "task_name": "规划失败",
        "description": f"[规划失败] {error_msg}",
        "nodes": [],
        "edges": [],
    }


def refine_node(
    node: dict[str, Any],
    user_input: str,
    category: str,
    req_id: str,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    """
    对单个计划节点进行 LLM 细化，补全 name/detail/meta。

    ✅ 增加完整异常兜底，始终返回包含 name/detail/meta 的合法结构。
    ✅ Mock 路径支持 cancel_event 取消感知。
    ✅ 入参防御 + 归一化后二次校验，双重保障返回结构完整性。
    """
    # ── 定义本函数的返回结构契约 ────────────────────────
    # 集中管理，避免成功/失败/兜底三处字段名不一致
    _REFINE_REQUIRED_KEYS = ("name", "details", "meta")

    def _fallback_result(error_msg: str, original_node: dict) -> dict[str, Any]:
        """生成降级返回对象，保留原始节点信息供上游决策"""
        return {
            "name": original_node.get("name", "未命名节点"),
            "details": f"[细化失败] {error_msg}",
            "meta": {"refine_error": error_msg, "fallback": True},
        }

    # ── 入参防御 ────────────────────────────────────────
    if not isinstance(node, dict):
        logger.error(
            "[Refine] node 类型非法: %s (req=%s)",
            type(node).__name__, req_id,
        )
        return _fallback_result("node参数类型非法", {})

    # ── Mock 短路（含取消感知）──────────────────────────
    if USE_MOCK_LLM:
        if cancel_event and cancel_event.is_set():
            raise TimeoutError("Mock: cancelled by event")
        return _mock_refine(req_id)

    # ── LLM 调用 + 解析 + 归一化 + 异常兜底 ───────────
    try:
        prompt = _render_template(
            NODE_REFINE_PROMPT, req_id,
            node_json=json.dumps(node, ensure_ascii=False),
            user_input=user_input,
            category=category,
        )

        raw = _call_llm(
            model=LLM_NODE_MODEL,
            prompt=prompt,
            enable_thinking=LLM_NODE_ENABLE_THINKING,
            req_id=req_id,
            timeout=LLM_NODE_TIMEOUT,
            cancel_event=cancel_event,
        )

        result = _extract_json(raw)
        result = _normalize_llm_output(
            result, expected_keys=list(_REFINE_REQUIRED_KEYS),
        )

        # ✅ 归一化后二次校验：确保所有必要字段都存在且非 None
        for key in _REFINE_REQUIRED_KEYS:
            if key not in result or result[key] is None:
                logger.warning(
                    "[Refine] 归一化后仍缺少字段 '%s'，使用原始节点值兜底 (req=%s)",
                    key, req_id,
                )
                result[key] = node.get(key, "")

        return result

    except TimeoutError:
        logger.error("[Refine] 节点细化超时 (req=%s)", req_id)
        return _fallback_result("节点细化超时", node)
    except ValueError as e:
        logger.error("[Refine] 节点细化解析格式错误: %s (req=%s)", e, req_id)
        return _fallback_result("节点细化解析格式错误", node)
    except RuntimeError as e:
        logger.error("[Refine] 节点细化服务异常: %s (req=%s)", e, req_id)
        return _fallback_result("节点细化服务异常", node)
    except Exception as e:
        logger.exception("[Refine] 节点细化未知异常: %s (req=%s)", e, req_id)
        return _fallback_result("节点细化异常", node)

# ══════════════════════════════════════════════════
#  Mock（仅测试用）
# ══════════════════════════════════════════════════


def _mock_intent(req_id: str) -> dict[str, Any]:
    return {"needs_planning": True, "category": "cooking",
            "summary": "Mock: 任务解析完成", "complexity": "medium"}


def _mock_plan(req_id: str) -> dict[str, Any]:
    return {
        "task_name": "Mock任务", "description": "Mock模式生成的计划",
        "nodes": [
            {"id": 1, "name": "准备食材", "details": "洗切西红柿和鸡蛋"},
            {"id": 2, "name": "炒鸡蛋", "details": "热油炒散鸡蛋盛出"},
            {"id": 3, "name": "炒西红柿", "details": "炒出汤汁加糖"},
            {"id": 4, "name": "合并出锅", "details": "倒入鸡蛋混合均匀"},
        ],
        "edges": [
            {"from": 1, "to": 2, "label": "食材就绪"},
            {"from": 2, "to": 3, "label": "鸡蛋炒好"},
            {"from": 3, "to": 4, "label": "西红柿出汁"},
        ],
    }


def _mock_refine(req_id: str) -> dict[str, Any]:
    return {
        "name": "Mock: 执行核心步骤",
        "details": "1. 准备工具\n2. 执行操作\n3. 验证结果",
        "meta": {
            "preconditions": ["前置条件已满足"],
            "postconditions": ["预期结果达成"],
            "retry_policy": "失败后重试最多3次",
        },
    }
