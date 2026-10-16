
"""
规划器Agent
===========
负责任务拆解、步骤规划、工具选择。

核心能力：
- 将复杂任务拆解为可执行的子步骤
- 为每个步骤匹配合适的工具/Skill
- 评估任务难度与风险等级
- 生成结构化的执行计划
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from .base import BaseAgent
from ..harness import TaskContext


# 结构化输出模型（1.x标准方案，替代手动JSON解析）
class PlanStep(BaseModel):
    step_id: int = Field(description="步骤序号")
    description: str = Field(description="步骤详细描述")
    tool: Optional[str] = Field(description="使用的工具名称，无需工具则为null")
    risk_level: str = Field(description="风险等级：low/medium/high")
    expected_output: str = Field(description="步骤预期输出")


class TaskPlan(BaseModel):
    task_analysis: str = Field(description="任务分析与理解")
    difficulty: str = Field(description="任务难度：easy/medium/hard")
    steps: List[PlanStep] = Field(description="执行步骤列表")
    overall_strategy: str = Field(description="整体执行策略说明")


class PlannerAgent(BaseAgent):
    role = "planner"
    system_prompt_key = "planner_agent"

    async def plan(self, task: TaskContext) -> dict:
        """生成执行计划（1.x原生结构化输出，保证JSON格式正确）"""
        available_tools = [t.name for t in self.skill_registry.get_all_tools()]
        history = task.execution_results[-3:
                                         ] if task.execution_results else "无"

        # 1.x原生结构化输出绑定
        structured_llm = self.llm.with_structured_output(TaskPlan)

        prompt = f"""
请分析以下任务，制定详细的执行计划。
任务：{task.query}
当前迭代：第 {task.iteration_count} 轮
历史执行结果：{history}
可用工具列表：{', '.join(available_tools)}

要求：
1. 步骤具体可执行，避免笼统描述
2. 合理选择工具，禁止滥用
3. 高风险操作（如删除文件、执行系统命令）必须标记为high风险等级
4. 多轮迭代场景下，重点针对历史问题优化调整
        """

        try:
            plan_obj: TaskPlan = await structured_llm.ainvoke([
                ("system", self.get_system_prompt()),
                ("human", prompt),
            ])
            return plan_obj.model_dump()
        except Exception:
            # 极端降级兜底
            return {
                "task_analysis": task.query,
                "difficulty": "medium",
                "steps": [{
                    "step_id": 1,
                    "description": f"执行任务：{task.query}",
                    "tool": None,
                    "risk_level": "low",
                    "expected_output": "任务执行结果",
                }],
                "overall_strategy": "直接执行",
            }

    async def run(self, *args, **kwargs):
        return await self.plan(*args, **kwargs)
