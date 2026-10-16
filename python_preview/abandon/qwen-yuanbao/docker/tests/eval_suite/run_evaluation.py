"""
run_evaluation.py — Task Planner v6.0 评估套件总编排入口
运行: python -m eval_suite.run_evaluation [--mock|--real] [--mongo-uri URI]
"""
import argparse
import os
import sys
import time
from datetime import datetime, timezone, timedelta

# ── 环境注入 (最先执行) ──
def parse_global_args():
    p = argparse.ArgumentParser(description="Task Planner 评估套件")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_true", default=True, help="Mock 模式 (默认)")
    g.add_argument("--real", action="store_true", help="真实 API 模式")
    p.add_argument("--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"), help="MongoDB URI")
    p.add_argument("--skip-hitl-export", action="store_true", help="跳过 SFT 导出")
    return p.parse_args()

ARGS = parse_global_args()
os.environ["USE_MOCK_LLM"] = "true" if ARGS.mock else "false"

# ── 导入子模块 ──
from eval_suite.dataset_manager import DatasetManager
from eval_suite.crucible_eval import CrucibleEvaluator, _score_to_status
from eval_suite.hitl_reviewer import HITLReviewer


def print_banner(mode: str):
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    print("=" * 70)
    print("🔥 Task Planner v6.0 熔炉评估套件 (Modular Edition)")
    print(f"   时间: {now:%Y-%m-%d %H:%M:%S}")
    print(f"   模式: {mode}")
    print("=" * 70)


def print_summary(report):
    print("\n" + "=" * 70)
    print("📋 评估总结")
    print("=" * 70)
    print(f"  用例: {report.passed_cases}✅ / {report.failed_cases}❌ / {report.error_cases}💥 (共 {report.total_cases})")
    print(f"  耗时: {report.total_duration_ms}ms\n")
    print("  五维平均分:")
    for dim, avg in report.dimension_averages.items():
        bar = "█" * int(avg * 3) + "░" * (30 - int(avg * 3))
        print(f"    {dim:<12} {avg:>5.1f}  {bar}  {_score_to_status(avg)}")
    
    rate = report.passed_cases / max(report.total_cases, 1)
    grade = "A 🏆" if rate >= 0.8 else ("B ⚠️" if rate >= 0.6 else "C 🚨")
    print(f"\n  综合评级: {grade}")
    print("=" * 70)


def main():
    t0 = time.time()
    mode = "Mock" if ARGS.mock else "Real API"
    print_banner(mode)

    # ── Step 1: 加载数据集 ──
    print("\n📚 Step 1: 加载测试数据集...")
    ds_mgr = DatasetManager(mongo_uri=ARGS.mongo_uri)
    cases = ds_mgr.load_active_cases()
    print(f"   已加载 {len(cases)} 条用例")

    if not cases:
        print("❌ 无可用测试用例，退出"); sys.exit(1)

    # ── Step 2: 执行评估 ──
    print(f"\n🎯 Step 2: 执行评估 ({mode})...")
    evaluator = CrucibleEvaluator(use_mock=ARGS.mock)
    report = evaluator.run(cases)

    # ── Step 3: MongoDB 持久化 (可选) ──
    print("\n💾 Step 3: 持久化到 MongoDB...")
    try:
        from pymongo import MongoClient
        client = MongoClient(ARGS.mongo_uri, serverSelectionTimeoutMS=3000)
        db = client["task_planner_db"]
        
        # 保存 run 元数据
        from dataclasses import asdict
        run_doc = {k: v for k, v in asdict(report).items() if k != "case_results"}
        db.eval_runs.update_one({"run_id": report.run_id}, {"$set": run_doc}, upsert=True)
        
        # 保存用例结果
        for cr in report.case_results:
            db.eval_results.update_one(
                {"run_id": report.run_id, "case_id": cr.case_id},
                {"$set": asdict(cr)}, upsert=True
            )
        print(f"   ✅ MongoDB 已保存 {len(report.case_results)} 条结果")
    except Exception as e:
        print(f"   ⚠️ MongoDB 跳过: {e}")

    # ── Step 4: SFT 导出 (可选) ──
    if not ARGS.skip_hitl_export:
        print("\n📦 Step 4: 检查 SFT 语料导出...")
        reviewer = HITLReviewer(mongo_uri=ARGS.mongo_uri)
        count = reviewer.export_sft()
        if count == 0:
            print("   ℹ️ 暂无新的 SFT 语料 (可通过 --ui 启动审阅台标注)")

    # ── Step 5: 打印摘要 ──
    print_summary(report)

    elapsed = int((time.time() - t0) * 1000)
    print(f"\n⏱️  总耗时: {elapsed}ms")
    
    rate = report.passed_cases / max(report.total_cases, 1)
    sys.exit(0 if rate >= 0.6 else 1)


if __name__ == "__main__":
    main()
