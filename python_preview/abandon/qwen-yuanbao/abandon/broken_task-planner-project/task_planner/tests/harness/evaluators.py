"""
evaluators.py — Agent 能力评估器
══════════════════════════════════
对 Harness 产出的原始结果做多维度评分：
  ✅ 意图识别准确率（和人工标注对比）
  ✅ 规划合理性（成功标志/节点数/耗时）
  ✅ 端到端成功率 + 耗时分桶
"""
from typing import Dict, Any, List, Optional

from .agent_harness import AgentRunResult, AgentHarness


def eval_intent(
    result: AgentRunResult,
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    """对比 agent 输出的意图判断 vs 人工标注的期望"""
    output = result.output
    score = 0
    details: Dict[str, Any] = {}

    actual_planning = bool(output.get("svg") or output.get("task_id"))
    expected_planning = expected.get("needs_planning", True)

    planning_ok = (actual_planning == expected_planning)
    details["planning_match"] = planning_ok
    details["actual_has_plan"] = actual_planning
    details["expected_needs_planning"] = expected_planning
    score += 1 if planning_ok else 0

    details["category_expected"] = expected.get("category", "?")

    return {
        "case_id": result.case_id,
        "dimension": "intent",
        "score": score,
        "max_score": 1,
        "pass": score == 1,
        "details": details,
    }


def eval_planning(
    result: AgentRunResult,
    expected: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """评估规划输出是否合理"""
    output = result.output
    score = 0
    max_score = 4
    details: Dict[str, Any] = {}

    if output.get("success"):
        score += 1
        details["e2e_success"] = True
    else:
        details["e2e_success"] = False
        details["error"] = output.get("error", "")

    if output.get("task_id"):
        score += 1
        details["has_task_id"] = True
    else:
        details["has_task_id"] = False

    svg = output.get("svg", "")
    if svg and len(svg) > 100:
        score += 1
        details["has_svg"] = True
        details["svg_len"] = len(svg)
    else:
        details["has_svg"] = False

    elapsed_s = result.total_elapsed_ms / 1000
    if elapsed_s < 120:
        score += 1
        details["elapsed_ok"] = True
    else:
        details["elapsed_ok"] = False
        details["elapsed_s"] = round(elapsed_s, 1)

    return {
        "case_id": result.case_id,
        "dimension": "planning",
        "score": score,
        "max_score": max_score,
        "pass": score == max_score,
        "details": details,
    }


def eval_case(
    result: AgentRunResult,
    expected_intent: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """对一个 case 跑全部评估维度"""
    evaluations = []
    if expected_intent is not None:
        evaluations.append(eval_intent(result, expected_intent))
    evaluations.append(eval_planning(result))

    total_score = sum(e["score"] for e in evaluations)
    total_max = sum(e["max_score"] for e in evaluations)
    pass_count = sum(1 for e in evaluations if e["pass"])

    return {
        "case_id": result.case_id,
        "total_score": total_score,
        "total_max": total_max,
        "pass_count": pass_count,
        "pass_rate": round(pass_count / len(evaluations) * 100, 1) if evaluations else 0,
        "evaluations": evaluations,
    }


def eval_batch(
    harness: AgentHarness,
    expectations: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """对 harness 里的全部结果做评估"""
    expectations = expectations or {}
    case_reports = []
    for result in harness.all_results():
        expected = expectations.get(result.case_id)
        report = eval_case(result, expected)
        case_reports.append(report)

    total_cases = len(case_reports)
    if total_cases == 0:
        return {"total_cases": 0}

    total_pass = sum(1 for r in case_reports if r["pass_count"] == len(r["evaluations"]))
    avg_pass_rate = sum(r["pass_rate"] for r in case_reports) / total_cases

    dim_stats: Dict[str, Dict[str, Any]] = {}
    for report in case_reports:
        for ev in report["evaluations"]:
            dim = ev["dimension"]
            if dim not in dim_stats:
                dim_stats[dim] = {"scores": [], "maxes": []}
            dim_stats[dim]["scores"].append(ev["score"])
            dim_stats[dim]["maxes"].append(ev["max_score"])

    dim_summary = {}
    for dim, st in dim_stats.items():
        if st["maxes"]:
            dim_summary[dim] = {
                "avg_score": round(sum(st["scores"]) / len(st["scores"]), 2),
                "avg_pct": round(sum(st["scores"]) / sum(st["maxes"]) * 100, 1),
            }

    return {
        "total_cases": total_cases,
        "fully_passed": total_pass,
        "avg_pass_rate": round(avg_pass_rate, 1),
        "dimension_summary": dim_summary,
        "case_reports": case_reports,
        "harness_summary": harness.summary(),
    }
