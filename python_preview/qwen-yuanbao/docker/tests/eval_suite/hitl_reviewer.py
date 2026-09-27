"""
hitl_reviewer.py — Human-in-the-Loop 审阅台 & SFT 导出器
独立运行: python -m eval_suite.hitl_reviewer
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
_SFT_OUTPUT_DIR = _PROJECT_ROOT / "sft_exports"
_SFT_OUTPUT_DIR.mkdir(exist_ok=True)

_MONGO_AVAILABLE = False
try:
    from pymongo import MongoClient
    _MONGO_AVAILABLE = True
except ImportError:
    pass


class HITLReviewer:
    """HITL 审阅核心逻辑 (与 UI 解耦)"""

    def __init__(self, mongo_uri: Optional[str] = None, db_name: str = "task_planner_db"):
        self.db = None
        if _MONGO_AVAILABLE and mongo_uri:
            try:
                client = MongoClient(mongo_uri, serverSelectionTimeoutMS=3000)
                self.db = client[db_name]
            except Exception:
                pass

    def get_pending_reviews(self, limit: int = 50) -> list:
        """获取待审阅用例 (score 4~7 或安全类未审阅)"""
        if not self.db:
            return []
        return list(self.db.eval_results.find({
            "$or": [
                {"overall_score": {"$gte": 4, "$lte": 7}},
                {"dimensions.name": "安全合规", "dimensions.score": {"$lte": 8}}
            ],
            "is_human_reviewed": {"$ne": True}
        }).limit(limit))

    def submit_review(self, run_id: str, case_id: str, score: float,
                      status: str, feedback: str, is_sft: bool) -> bool:
        """提交人工审阅结果"""
        if not self.db:
            return False
        self.db.eval_results.update_one(
            {"run_id": run_id, "case_id": case_id},
            {"$set": {
                "is_human_reviewed": True,
                "human_overall_score": score,
                "human_status": status,
                "human_feedback": feedback,
                "is_perfect_sft": is_sft,
                "reviewed_at": datetime.now().isoformat()
            }}
        )
        return True

    def export_sft(self, output_file: Optional[str] = None) -> int:
        """导出人工标记的完美 SFT 语料"""
        if not self.db:
            print("[HITL] ❌ MongoDB 不可用")
            return 0

        out_path = output_file or str(
            _SFT_OUTPUT_DIR / f"sft_{datetime.now():%Y%m%d_%H%M%S}.jsonl")
        cursor = self.db.eval_results.find(
            {"is_perfect_sft": True, "is_human_reviewed": True})

        count = 0
        with open(out_path, "w", encoding="utf-8") as f:
            for doc in cursor:
                record = {
                    "instruction": f"请为以下用户需求生成任务执行计划:\n\n{doc.get('input_text', '')}",
                    "output": json.dumps(doc.get("plan_result", {}), ensure_ascii=False, indent=2),
                    "metadata": {
                        "source": "hitl_reviewed",
                        "human_score": doc.get("human_overall_score"),
                        "case_id": doc.get("case_id")
                    }
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

        print(f"[HITL] 🎉 导出 {count} 条 SFT 语料 → {out_path}")
        return count


def launch_gradio_ui(mongo_uri: Optional[str] = None):
    """启动 Gradio 审阅界面"""
    try:
        import gradio as gr
    except ImportError:
        print("[HITL] ❌ gradio 未安装: pip install gradio")
        return

    reviewer = HITLReviewer(mongo_uri=mongo_uri)

    with gr.Blocks(title="👨‍⚖️ HITL 审阅台") as demo:
        gr.Markdown("# 👨‍⚖️ Task Planner HITL 审阅台\n> 审阅争议用例，覆盖评分，积累 SFT 语料")

        pending = reviewer.get_pending_reviews()
        choices = [f"{r['run_id']} | {r['case_id']} | {
            r.get('input_preview', '')}" for r in pending]

        selector = gr.Dropdown(choices, label="选择待审阅用例", interactive=True)
        display_input = gr.Markdown(label="用户输入")
        display_plan = gr.Code(label="LLM 生成的 Plan", language="json")
        judge_info = gr.Markdown(label="LLM Judge 自动评分")

        with gr.Row():
            h_score = gr.Slider(0, 10, label="人工评分", step=0.5)
            h_status = gr.Dropdown(
                ["优秀", "良好", "及格", "需改进", "严重缺陷"], label="人工定性")
        h_feedback = gr.Textbox(label="专家 Feedback", lines=3)
        h_sft = gr.Checkbox(label="🌟 标记为完美 SFT 语料")
        btn = gr.Button("✅ 提交审阅", variant="primary")
        msg = gr.Markdown()

        def load(sel):
            if not sel:
                return "", "{}", ""
            rid, cid = sel.split(" | ")[:2]
            doc = reviewer.db.eval_results.find_one(
                {"run_id": rid, "case_id": cid}) if reviewer.db else None
            if not doc:
                return "未找到", "{}", ""
            plan = json.dumps(doc.get("plan_result", {}),
                              ensure_ascii=False, indent=2)
            dims = "\n".join([f"- **{d['name']}**: {d['score']}分 — {
                             d.get('feedback', '')}" for d in doc.get("dimensions", [])])
            return f"**Input**: {doc.get('input_text', '')}", plan, dims

        def submit(sel, sc, st, fb, sft):
            if not sel:
                return "❌ 请选择用例"
            rid, cid = sel.split(" | ")[:2]
            ok = reviewer.submit_review(rid, cid, sc, st, fb, sft)
            return "✅ 审阅已保存!" if ok else "❌ 保存失败"

        selector.change(load, selector, [
                        display_input, display_plan, judge_info])
        btn.click(submit, [selector, h_score,
                  h_status, h_feedback, h_sft], msg)

    demo.launch(server_name="0.0.0.0", server_port=7861)


# ══════════════════════════════════════════════════
# 独立运行入口
# ══════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HITL Reviewer")
    parser.add_argument(
        "--mongo-uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument(
        "--export-sft", action="store_true", help="仅导出 SFT 数据集")
    parser.add_argument("--ui", action="store_true", help="启动 Gradio UI")
    args = parser.parse_args()

    reviewer = HITLReviewer(mongo_uri=args.mongo_uri)

    if args.export_sft:
        reviewer.export_sft()
    elif args.ui:
        launch_gradio_ui(mongo_uri=args.mongo_uri)
    else:
        print("用法: python -m eval_suite.hitl_reviewer --ui 或 --export-sft")
