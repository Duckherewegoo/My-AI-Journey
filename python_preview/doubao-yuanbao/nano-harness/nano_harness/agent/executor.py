"""
执行器Agent
===========
负责具体执行规划好的步骤，调用工具/Skill完成任务。

核心能力：
- Function Calling：自动调用合适的工具
- 多模态处理：处理图片、视频、音频
- Bash执行：运行Linux命令（带确认）
- 错误处理：执行失败时的重试与降级
"""

import json
from typing import Dict, List, Any

from .base import BaseAgent
from ..harness import TaskContext


class ExecutorAgent(BaseAgent):
    """执行器智能体 - 工具调用专家"""
    
    role = "executor"
    system_prompt_key = "executor_agent"
    
    async def execute(self, task: TaskContext) -> List[Dict[str, Any]]:
        """
        执行计划中的所有步骤
        
        高级技巧：
        - 逐步执行，每步都检查结果
        - 失败自动重试（最多2次）
        - 结果质量检查
        - 上下文传递：上一步结果作为下一步输入
        """
        results = []
        steps = task.plan.get("steps", [])
        
        for i, step in enumerate(steps):
            step_result = await self._execute_step(task, step, results)
            results.append(step_result)
            
            # 检查是否失败，失败则重试一次
            if step_result.get("status") == "failed" and step.get("retry", True):
                retry_result = await self._execute_step(task, step, results, retry=True)
                if retry_result.get("status") == "success":
                    results[-1] = retry_result
        
        return results
    
    async def _execute_step(
        self,
        task: TaskContext,
        step: Dict,
        previous_results: List[Dict],
        retry: bool = False,
    ) -> Dict[str, Any]:
        """执行单个步骤"""
        step_id = step.get("step_id", 0)
        tool_name = step.get("tool")
        description = step.get("description", "")
        risk_level = step.get("risk_level", "low")
        
        try:
            if tool_name and tool_name != "null":
                # 有指定工具，使用Function Calling执行
                # 构建上下文：之前的执行结果
                context = self._build_execution_context(task, previous_results)
                
                result = await self.invoke_with_tools(
                    query=f"请执行以下步骤：{description}\n\n参考上下文：{context}",
                    system_context={"step": step, "retry": retry},
                )
                
                return {
                    "step_id": step_id,
                    "tool": tool_name,
                    "description": description,
                    "status": "success",
                    "result": result["output"],
                    "tool_calls": result["tool_calls"],
                    "risk_level": risk_level,
                    "retry": retry,
                }
            else:
                # 不需要工具，直接思考回答
                context = self._build_execution_context(task, previous_results)
                result = await self.simple_chat(
                    f"请完成以下任务：{description}\n\n参考信息：{context}"
                )
                
                return {
                    "step_id": step_id,
                    "tool": None,
                    "description": description,
                    "status": "success",
                    "result": result,
                    "tool_calls": [],
                    "risk_level": risk_level,
                    "retry": retry,
                }
        
        except Exception as e:
            return {
                "step_id": step_id,
                "tool": tool_name,
                "description": description,
                "status": "failed",
                "error": str(e),
                "risk_level": risk_level,
                "retry": retry,
            }
    
    def _build_execution_context(self, task: TaskContext, results: List[Dict]) -> str:
        """构建执行上下文 - 把之前的结果整理成可读格式"""
        if not results:
            return "暂无之前的执行结果"
        
        context_parts = []
        for r in results[-3:]:  # 只保留最近3个结果，避免上下文过长
            status = r.get("status", "unknown")
            desc = r.get("description", "")
            result_preview = str(r.get("result", ""))[:500]
            context_parts.append(f"[{status}] {desc}\n结果摘要：{result_preview}")
        
        return "\n\n".join(context_parts)
    
    async def run(self, *args, **kwargs):
        return await self.execute(*args, **kwargs)
