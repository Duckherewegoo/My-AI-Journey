"""
协调器Agent
===========
负责最终汇总、生成用户友好的回答。

核心能力：
- 结果整合：将多步骤的执行结果整合成连贯的回答
- 风格适配：根据用户偏好调整回答风格
- 信息提炼：从大量信息中提取关键点
- 结构化输出：按用户需求组织输出格式

这是用户直接接触的"门面"Agent，负责最终交付体验。
"""

import json
from typing import Dict, Any

from .base import BaseAgent
from ..harness import TaskContext


class CoordinatorAgent(BaseAgent):
    """协调器智能体 - 最终输出专家"""
    
    role = "coordinator"
    system_prompt_key = "coordinator_agent"
    
    async def summarize(self, task: TaskContext) -> str:
        """
        汇总所有执行结果，生成最终回答
        
        高级技巧：
        - 信息分层：核心结论前置，细节后置
        - 结构化输出：使用标题、列表、表格等增强可读性
        - 上下文感知：记住用户之前的偏好和历史
        - 元信息隐藏：把执行过程的技术细节藏起来，只给用户看结果
        """
        # 整理所有信息
        results_summary = self._compile_results(task)
        
        prompt = f"""
请根据以下任务执行过程，生成最终的用户回答。

【用户原始问题】
{task.query}

【执行过程与结果】
{results_summary}

【迭代次数】共 {task.iteration_count} 轮

请生成最终回答，要求：
1. 直接回答用户问题，不要提及"执行过程"、"步骤"、"Agent"等内部技术细节
2. 核心结论前置，详细说明后置
3. 结构清晰，使用合适的标题、列表、加粗等格式
4. 语言自然流畅，像真人在回答
5. 如果有失败的步骤，巧妙地绕过或用其他方式弥补，不要暴露失败
6. 回答要完整、实用、有价值

记住：你是在直接和用户对话，不是在写报告。
"""
        
        result = await self.simple_chat(prompt)
        return result
    
    def _compile_results(self, task: TaskContext) -> str:
        """编译所有执行结果"""
        parts = []
        
        # 任务分析
        if task.plan:
            parts.append(f"## 任务分析\n{task.plan.get('task_analysis', '')}")
            parts.append(f"## 执行策略\n{task.plan.get('overall_strategy', '')}")
        
        # 执行结果
        parts.append("## 执行结果")
        for i, r in enumerate(task.execution_results):
            status = r.get("status", "unknown")
            desc = r.get("description", f"步骤{i+1}")
            
            if status == "success":
                result_text = str(r.get("result", ""))
                # 截断过长的结果
                if len(result_text) > 1000:
                    result_text = result_text[:1000] + "\n... [内容过长，已截断]"
                parts.append(f"### {desc} ✅\n{result_text}")
            else:
                error = r.get("error", "未知错误")
                parts.append(f"### {desc} ❌\n失败原因：{error}")
        
        # 评审意见
        if task.critique:
            parts.append(f"## 质量评审\n{task.critique}")
        
        return "\n\n".join(parts)
    
    async def run(self, *args, **kwargs):
        return await self.summarize(*args, **kwargs)
