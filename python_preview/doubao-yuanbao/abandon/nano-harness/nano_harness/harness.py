"""
Harness 核心编排引擎
====================
这是整个系统的"驾驭"大脑，负责任务拆解、智能体调度、状态管理、结果汇总。

核心特性：
- 多智能体协作：规划器 → 执行器 → 批评家 → 协调器 的闭环工作流
- 状态机驱动：每个任务都有完整的生命周期状态追踪
- 动态工具加载：根据任务自动匹配Skill与工具
- 人机介入点：关键决策点可暂停等待用户确认
- 上下文记忆：跨轮次的对话与任务状态记忆
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage

from .agent.base import BaseAgent
from .agent.coordinator import CoordinatorAgent
from .agent.planner import PlannerAgent
from .agent.executor import ExecutorAgent
from .agent.critic import CriticAgent
from .skills.registry import SkillRegistry
from .prompts.templates import PromptTemplateEngine
from .prompts.optimizer import PromptOptimizer


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"           # 待处理
    PLANNING = "planning"         # 规划中
    EXECUTING = "executing"       # 执行中
    CRITIQUING = "critiquing"     # 评审中
    WAITING_USER = "waiting_user" # 等待用户确认
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败


@dataclass
class TaskContext:
    """任务上下文 - 保存任务全生命周期状态"""
    task_id: str
    query: str
    status: TaskStatus = TaskStatus.PENDING
    messages: List[BaseMessage] = field(default_factory=list)
    plan: Optional[Dict] = None
    execution_results: List[Dict] = field(default_factory=list)
    critique: Optional[str] = None
    final_result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    user_decisions: List[Dict] = field(default_factory=list)
    iteration_count: int = 0
    max_iterations: int = 5


@dataclass
class HarnessConfig:
    """Harness配置"""
    max_iterations: int = 5
    enable_critique: bool = True
    enable_human_in_the_loop: bool = True
    auto_load_skills: bool = True
    default_model: str = "gpt-4o"


class Harness:
    """
    NanoHarness 核心编排器
    
    这是整个框架的入口，负责任务的全生命周期管理：
    1. 接收用户请求
    2. 规划器拆解任务
    3. 执行器调用工具/Skill执行
    4. 批评家评审结果
    5. 如需迭代则回到规划器
    6. 最终汇总返回结果
    
    高级技巧：
    - 反思循环：执行 → 批评 → 修正 的自我迭代机制
    - 动态工具选择：根据任务上下文自动加载最合适的Skill
    - 置信度门控：低置信度结果自动触发用户确认
    """
    
    def __init__(
        self,
        llm: BaseChatModel,
        config: Optional[HarnessConfig] = None,
        skill_registry: Optional[SkillRegistry] = None,
        user_confirm_callback: Optional[Callable] = None,
    ):
        self.llm = llm
        self.config = config or HarnessConfig()
        self.skill_registry = skill_registry or SkillRegistry()
        self.user_confirm_callback = user_confirm_callback or self._default_confirm
        
        # 提示词引擎
        self.prompt_engine = PromptTemplateEngine()
        self.prompt_optimizer = PromptOptimizer()
        
        # 初始化智能体群
        self.agents: Dict[str, BaseAgent] = {}
        self._init_agents()
        
        # 任务存储
        self._tasks: Dict[str, TaskContext] = {}
        
    def _init_agents(self):
        """初始化所有智能体"""
        agent_kwargs = {
            "llm": self.llm,
            "prompt_engine": self.prompt_engine,
            "skill_registry": self.skill_registry,
        }
        
        self.agents["coordinator"] = CoordinatorAgent(**agent_kwargs)
        self.agents["planner"] = PlannerAgent(**agent_kwargs)
        self.agents["executor"] = ExecutorAgent(**agent_kwargs)
        self.agents["critic"] = CriticAgent(**agent_kwargs)
    
    def create_task(self, query: str, **metadata) -> TaskContext:
        """创建一个新任务"""
        task_id = str(uuid.uuid4())[:8]
        task = TaskContext(
            task_id=task_id,
            query=query,
            messages=[HumanMessage(content=query)],
            metadata=metadata,
            max_iterations=self.config.max_iterations,
        )
        self._tasks[task_id] = task
        return task
    
    async def run(self, query: str, **metadata) -> str:
        """
        执行一个完整任务 - 主入口
        
        工作流：
        1. 规划阶段：拆解任务，确定执行步骤
        2. 执行阶段：调用工具/Skill逐步执行
        3. 评审阶段：批评家检查结果质量
        4. 迭代：不达标则重新规划执行
        5. 汇总：协调器生成最终回答
        """
        task = self.create_task(query, **metadata)
        
        # 主循环 - 反思迭代机制
        while task.iteration_count < task.max_iterations:
            task.iteration_count += 1
            
            # 阶段1：规划
            task.status = TaskStatus.PLANNING
            task.plan = await self.agents["planner"].plan(task)
            
            # 阶段2：执行
            task.status = TaskStatus.EXECUTING
            results = await self.agents["executor"].execute(task)
            task.execution_results.extend(results)
            
            # 检查是否需要用户确认（人机交互点）
            if self.config.enable_human_in_the_loop:
                need_confirm = self._check_need_user_confirmation(task)
                if need_confirm:
                    task.status = TaskStatus.WAITING_USER
                    user_decision = await self._ask_user_confirmation(task, need_confirm)
                    task.user_decisions.append(user_decision)
                    if not user_decision.get("approved", True):
                        # 用户否决，重新规划
                        continue
            
            # 阶段3：评审
            if self.config.enable_critique:
                task.status = TaskStatus.CRITIQUING
                critique_result = await self.agents["critic"].critique(task)
                task.critique = critique_result.get("feedback")
                
                if critique_result.get("needs_revision", False):
                    # 需要修订，进入下一轮迭代
                    task.messages.append(AIMessage(
                        content=f"[第{task.iteration_count}轮评审] 需要改进：{critique_result['feedback']}"
                    ))
                    continue
            
            # 达标，退出循环
            break
        
        # 最终汇总
        task.status = TaskStatus.COMPLETED
        final_result = await self.agents["coordinator"].summarize(task)
        task.final_result = final_result
        
        return final_result
    
    def _check_need_user_confirmation(self, task: TaskContext) -> Optional[Dict]:
        """
        检查是否需要用户确认
        高级技巧：置信度门控 + 风险评估
        """
        # 检查执行结果中的高风险操作
        for result in task.execution_results[-3:]:  # 只看最近的
            if result.get("risk_level") == "high":
                return {
                    "reason": "检测到高风险操作",
                    "operation": result.get("tool", "unknown"),
                    "preview": str(result.get("result", ""))[:200],
                }
            if result.get("tool") == "bash" and result.get("needs_confirm", True):
                return {
                    "reason": "Bash命令执行需要确认",
                    "operation": result.get("command", ""),
                    "preview": result.get("description", ""),
                }
        return None
    
    async def _ask_user_confirmation(self, task: TaskContext, reason: Dict) -> Dict:
        """询问用户确认"""
        try:
            result = await self.user_confirm_callback(task, reason)
            return result if isinstance(result, dict) else {"approved": result}
        except Exception:
            # 默认放行（安全模式下应默认拒绝）
            return {"approved": True, "reason": "自动放行"}
    
    def _default_confirm(self, task: TaskContext, reason: Dict) -> bool:
        """默认确认回调 - 实际使用时应替换为真实交互"""
        print(f"\n⚠️  需要确认: {reason['reason']}")
        print(f"   操作: {reason['operation']}")
        print(f"   预览: {reason.get('preview', '')}")
        return True  # 默认放行，生产环境应改为交互确认
    
    def get_task(self, task_id: str) -> Optional[TaskContext]:
        """获取任务状态"""
        return self._tasks.get(task_id)
    
    def register_skill(self, skill):
        """注册Skill - 动态扩展能力"""
        self.skill_registry.register(skill)
        # 通知所有Agent刷新工具列表
        for agent in self.agents.values():
            agent.refresh_tools()
    
    def optimize_prompt(self, prompt: str, task_type: str = "general") -> str:
        """
        提示词工程小技巧 - 自动优化提示词
        这是一个进阶功能，根据任务类型自动增强提示词效果
        """
        return self.prompt_optimizer.optimize(prompt, task_type)
