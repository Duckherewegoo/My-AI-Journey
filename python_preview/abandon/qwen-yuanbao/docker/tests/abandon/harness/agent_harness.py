"""
agent_harness.py — Agent 评估 Harness（生产级）
══════════════════════════════════════════
把整个 task_planner.agent 当黑盒包住：
  ✅ 喂输入 → 捕获输出 → 记录每一步耗时/状态
  ✅ 不修改 agent 一行代码（通过 task_agent.run 入口）
  ✅ 自动注入独立 req_id，日志可追踪
  ✅ 捕获异常，不中断评估流程
  ✅ 产出结构化结果，供 evaluators 打分
"""

from task_planner.llm_client import recognize_intent, generate_plan, refine_node
from task_planner.flowchart_pro import render_for_gradio
from task_planner.database import create_task_with_plan, update_node_status
from task_planner.agent import task_agent
import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# 导入被测对象（不 mock，走真实链路）
from task_planner.logger_setup import get_logger, set_req_id

logger = get_logger("harness")

# 统一用这个


@dataclass
class StepRecord:
    """单步执行记录"""

    step: str  # intent / plan / refine / execute / render
    success: bool
    elapsed_ms: int
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    """单次 agent 运行的完整记录"""

    case_id: str
    input: str
    req_id: str
    success: bool
    total_elapsed_ms: int
    steps: list[StepRecord] = field(default_factory=list)
    output: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class AgentHarness:
    """
    Agent 评估 Harness。

    用法：
        harness = AgentHarness()
        result = harness.run_case("cook_001", "教我做甜口西红柿炒鸡蛋")
        print(result.success, result.total_elapsed_ms)
    """

    def __init__(self, enable_refine: bool = True):
        self.enable_refine = enable_refine
        self._results: list[AgentRunResult] = []

    # ── 公共接口 ──────────────────────────────
    def run_case(self, case_id: str, user_input: str) -> AgentRunResult:
        """跑一个测试用例，返回结构化结果"""
        rid = set_req_id()  # 独立 req_id
        logger.info("[Harness] ▶ 开始用例 %s req=%s", case_id, rid)

        result = AgentRunResult(
            case_id=case_id,
            input=user_input,
            req_id=rid,
            success=False,
            total_elapsed_ms=0,
        )
        t0 = time.time()

        try:
            # ── 调用真实 agent（不 mock） ──
            agent_output = task_agent.run(
                user_input=user_input,
                req_id=rid,
                enable_refine=self.enable_refine,
            )

            elapsed = int((time.time() - t0) * 1000)
            result.total_elapsed_ms = elapsed
            result.output = agent_output
            result.success = bool(agent_output.get("success"))

            # ── 拆解 steps（agent 里有 result["steps"] 列表） ──
            for step_str in agent_output.get("steps", []):
                result.steps.append(
                    StepRecord(
                        step=step_str,
                        success=True,
                        elapsed_ms=0,
                        extra={"raw": step_str},
                    )
                )

            logger.info(
                "[Harness] ✅ 用例 %s 完成 | %dms | success=%s",
                case_id,
                elapsed,
                result.success,
            )

        except (RuntimeError, TimeoutError, ValueError) as e:
            elapsed = int((time.time() - t0) * 1000)
            result.total_elapsed_ms = elapsed
            result.error = f"{type(e).__name__}: {e}"
            result.steps.append(
                StepRecord(
                    step="exception",
                    success=False,
                    elapsed_ms=elapsed,
                    error=traceback.format_exc(),
                )
            )
            logger.error(
                "[Harness] ❌ 用例 %s 异常 | %dms | %s",
                case_id,
                elapsed,
                e,
            )

        self._results.append(result)
        return result

    def run_batch(self, cases: list[dict[str, str]]) -> list[AgentRunResult]:
        """批量跑用例"""
        results = []
        for case in cases:
            r = self.run_case(case["id"], case["input"])
            results.append(r)
        return results

    def all_results(self) -> list[AgentRunResult]:
        return list(self._results)

    def save_raw(self, path: str) -> None:
        """保存原始 JSON（供 reporters 画图/分析）"""
        data = [r.to_dict() for r in self._results]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("[Harness] 原始结果已保存 → %s", path)

    def summary(self) -> dict[str, Any]:
        """快速统计摘要"""
        total = len(self._results)
        if total == 0:
            return {"total": 0}
        success = sum(1 for r in self._results if r.success)
        elapsed_list = [r.total_elapsed_ms for r in self._results]
        return {
            "total": total,
            "success": success,
            "fail": total - success,
            "success_rate": round(success / total * 100, 1),
            "avg_ms": round(sum(elapsed_list) / total, 0),
            "min_ms": min(elapsed_list),
            "max_ms": max(elapsed_list),
            "p95_ms": sorted(elapsed_list)[int(total * 0.95)] if total > 1 else elapsed_list[0],
        }
