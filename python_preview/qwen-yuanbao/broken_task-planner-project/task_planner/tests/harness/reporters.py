"""
reporters.py — 评估报告生成器
════════════════════════════
  ✅ Markdown 报告（人读）
  ✅ JSON 报告（机器读 / CI 用）
"""
import json
import time
from typing import Dict, Any
from pathlib import Path


def to_markdown(report: Dict[str, Any]) -> str:
    """把评估结果渲染成 Markdown 报告"""
    lines = []
    lines.append("# 🤖 Task Planner Agent — 评估报告\n")
    lines.append(f"_生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}_\n")

    # 总览
    lines.append("## 📊 总览\n")
    lines.append(f"- 总用例数: **{report.get('total_cases', 0)}**")
    lines.append(f"- 全部通过: **{report.get('fully_passed', 0)}**")
    lines.append(f"- 平均通过率: **{report.get('avg_pass_rate', 0)}%**\n")

    # 维度
    lines.append("## 🎯 维度评分\n")
    dim = report.get("dimension_summary", {})
    if dim:
        lines.append("| 维度 | 平均得分 | 得分率 |")
        lines.append("|---|---|---|")
        for name, st in dim.items():
            lines.append(f"| {name} | {st['avg_score']} | {st['avg_pct']}% |")
        lines.append("")

    # Harness 摘要
    hs = report.get("harness_summary", {})
    if hs:
        lines.append("## ⏱️ 耗时统计\n")
        lines.append(f"- 成功率: **{hs.get('success_rate', 0)}%**")
        lines.append(f"- 平均: {hs.get('avg_ms', 0)}ms")
        lines.append(f"- 最快: {hs.get('min_ms', 0)}ms")
        lines.append(f"- 最慢: {hs.get('max_ms', 0)}ms")
        lines.append(f"- P95: {hs.get('p95_ms', 0)}ms\n")

    # 单用例明细
    lines.append("## 📋 用例明细\n")
    for case in report.get("case_reports", []):
        lines.append(f"### {case['case_id']}")
        lines.append(f"- 得分: {case['total_score']}/{case['total_max']}")
        lines.append(f"- 通过率: {case['pass_rate']}%")
        for ev in case.get("evaluations", []):
            icon = "✅" if ev["pass"] else "❌"
            lines.append(f"  - {icon} {ev['dimension']}: {ev['score']}/{ev['max_score']}")
            for k, v in ev.get("details", {}).items():
                lines.append(f"    - {k}: `{v}`")
        lines.append("")

    return "\n".join(lines)


def save_reports(
    report: Dict[str, Any],
    out_dir: str = "tests/output",
) -> Dict[str, str]:
    """同时保存 Markdown + JSON"""
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    md_path = Path(out_dir) / "eval_report.md"
    json_path = Path(out_dir) / "eval_report.json"

    md_path.write_text(to_markdown(report), encoding="utf-8")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"markdown": str(md_path), "json": str(json_path)}
