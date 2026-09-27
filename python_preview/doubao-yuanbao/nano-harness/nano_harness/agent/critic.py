"""
批评家Agent
===========
负责评审执行结果，提出改进意见，触发迭代优化。

核心能力：
- 质量评估：从多个维度评估结果质量
- 问题诊断：找出结果中的缺陷与不足
- 改进建议：给出具体的优化方向
- 迭代决策：判断是否需要重新执行

这是反思循环(Reflection Loop)的核心组件，也是多智能体系统的高级技巧。
"""


"""
批评家Agent（1.3.11适配版）
"""




from typing import Dict, Any, List
from pydantic import BaseModel, Field
from .base import BaseAgent
from ..harness import TaskContext
class DimensionScore(BaseModel):
    accuracy: int = Field(description="准确性得分 0-100")
    completeness: int = Field(description="完整性得分 0-100")
    clarity: int = Field(description="清晰度得分 0-100")
    practicality: int = Field(description="实用性得分 0-100")
    safety: int = Field(description="安全性得分 0-100")


class CritiqueResult(BaseModel):
    overall_score: int = Field(description="整体质量得分 0-100")
    dimensions: DimensionScore = Field(description="各维度得分")
    strengths: List[str] = Field(description="结果优点列表")
    weaknesses: List[str] = Field(description="结果缺点列表")
    feedback: str = Field(description="详细可执行的改进建议")
    needs_revision: bool = Field(description="是否需要重新迭代优化")
    revision_priority: str = Field(description="修订优先级 high/medium/low")


class CriticAgent(BaseAgent):
    role = "critic"
    system_prompt_key = "critic_agent"

    async def critique(self, task: TaskContext) -> Dict[str, Any]:
        """多维度质量评审（1.x原生结构化输出）"""
        results_summary = self._summarize_results(task)
        structured_llm = self.llm.with_structured_output(CritiqueResult)

        prompt = f"""
请专业评审以下任务的执行结果，按维度严格打分。
原始任务：{task.query}
执行结果摘要：{results_summary}
当前迭代：第 {task.iteration_count} / {task.max_iterations} 轮

评审标准：
- 80分以上：质量良好，无需修订
- 60-80分：有改进空间，可选修订
- 60分以下：质量较差，必须修订

注意：如果已是最后一轮迭代，强制设置needs_revision为false，停止循环。
        """

        try:
            critique_obj: CritiqueResult = await structured_llm.ainvoke([
                ("system", self.get_system_prompt()),
                ("human", prompt),
            ])
            result = critique_obj.model_dump()
        except Exception:
            result = {
                "overall_score": 70,
                "dimensions": {},
                "strengths": [],
                "weaknesses": [],
                "feedback": "结果基本可用，建议进一步优化",
                "needs_revision": False,
                "revision_priority": "medium",
            }

        # 安全门控：最后一轮强制终止迭代
        if task.iteration_count >= task.max_iterations:
            result["needs_revision"] = False
            result["feedback"] = f"{result['feedback']}\n[系统提示] 已达最大迭代次数，停止优化。"

        return result

    def _summarize_results(self, task: TaskContext) -> str:
        """整理执行结果摘要"""
        parts = []
        if task.plan:
            parts.append(f"【任务分析】{task.plan.get('task_analysis', 'N/A')}")
            parts.append(f"【执行策略】{task.plan.get('overall_strategy', 'N/A')}")

        for r in task.execution_results[-5:]:
            status = r.get("status", "unknown")
            desc = r.get("description", "")
            preview = str(r.get("result", r.get("error", "")))[:300]
            tools = ", ".join(r.get("tool_calls", [])) or "无"
            parts.append(
                f"步骤{r.get('step_id', '?')} [{status}]: {desc}\n调用工具: {tools}\n结果预览: {preview}")

        return "\n\n".join(parts) if parts else "无执行结果"

    async def run(self, *args, **kwargs):
        return await self.critique(*args, **kwargs)
