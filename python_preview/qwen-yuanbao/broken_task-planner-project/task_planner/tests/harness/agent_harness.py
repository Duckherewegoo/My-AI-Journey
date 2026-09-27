"""
agent_harness.py — Agent 评估 Harness（生产级）
════════════════════════════════════════════
把整个 task_planner.agent 当黑盒包住：
  ✅ 喂输入 → 捕获输出 → 记录每一步耗时/状态
  ✅ 不修改 agent 一行代码（通过 task_agent.run 入口）
  ✅ 自动注入独立 req_id，日志可追踪
  ✅ 捕获异常，不中断评估流程
  ✅ 产出结构化结果，供 evaluators 打分
"""
import time
import json
import traceback
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

from task_planner.agent import task_agent
from task_planner.logger_setup import set_req_id, get_logger

logger = get_logger("harness")


@dataclass
class StepRecord:
    """单步执行记录"""
    step: str
    success: bool
    elapsed_ms: int
    error: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRunResult:
    """单次 agent 运行的完整记录"""
    case_id: str
    input: str
    req_id: str
    success: bool
    total_elapsed_ms: int
    steps: List[StepRecord] = field(default_factory=list)
    output: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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
        self._results: List[AgentRunResult] = []

    def run_case(self, case_id: str, user_input: str) -> AgentRunResult:
        """跑一个测试用例，返回结构化结果"""
        rid = set_req_id()
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
            agent_output = task_agent.run(
                user_input=user_input,
                req_id=rid,
                enable_refine=self.enable_refine,
            )

            elapsed = int((time.time() - t0) * 1000)
            result.total_elapsed_ms = elapsed
            result.output = agent_output
            result.success = bool(agent_output.get("success"))

            for step_str in agent_output.get("steps", []):
                result.steps.append(StepRecord(
                    step=step_str,
                    success=True,
                    elapsed_ms=0,
                    extra={"raw": step_str},
                ))

            logger.info(
                "[Harness] ✅ 用例 %s 完成 | %dms | success=%s",
                case_id, elapsed, result.success,
            )

        except Exception as e:
            elapsed = int((time.time() - t0) * 1000)
            result.total_elapsed_ms = elapsed
            result.error = f"{type(e).__name__}: {e}"
            result.steps.append(StepRecord(
                step="exception",
                success=False,
                elapsed_ms=elapsed,
                error=traceback.format_exc(),
            ))
            logger.error(
                "[Harness] ❌ 用例 %s 异常 | %dms | %s",
                case_id, elapsed, e,
            )

        self._results.append(result)
        return result

    def run_batch(self, cases: List[Dict[str, str]]) -> List[AgentRunResult]:
        """批量跑用例"""
        return [self.run_case(c["id"], c["input"]) for c in cases]

    def all_results(self) -> List[AgentRunResult]:
        return list(self._results)

    def save_raw(self, path: str) -> None:
        """保存原始 JSON"""
        data = [r.to_dict() for r in self._results]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("[Harness] 原始结果已保存 → %s", path)

    def summary(self) -> Dict[str, Any]:
        """快速统计摘要"""
        total = len(self._results)
        if total == 0:
            return {"total": 0}
        success = sum(1 for r in self._results if r.success)
        elapsed_list = [r.total_elapsed_ms for r in self._results]
        elapsed_list.sort()
        return {
            "total": total,
            "success": success,
            "fail": total - success,
            "success_rate": round(success / total * 100, 1),
            "avg_ms": round(sum(elapsed_list) / total, 0),
            "min_ms": elapsed_list[0],
            "max_ms": elapsed_list[-1],
            "p95_ms": elapsed_list[int(total * 0.95)] if total > 1 else elapsed_list[0],
        }
