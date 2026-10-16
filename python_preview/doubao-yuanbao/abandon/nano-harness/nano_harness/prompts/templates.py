"""
提示词模板引擎
===============
管理和渲染各种提示词模板。

核心功能：
- 预设模板库：各种场景的高质量提示词
- 模板渲染：变量替换、条件渲染
- 模板继承：基础模板 + 扩展模板
- 动态加载：运行时添加新模板

每个Agent都有自己的系统提示词模板，
通过模板引擎统一管理和渲染。
"""

import re
from typing import Dict, Any, Optional, List
from string import Template


class PromptTemplateEngine:
    """
    提示词模板引擎
    
    提供模板管理和渲染功能，支持：
    - 变量替换
    - 条件片段
    - 模板继承
    - 动态注册
    """
    
    def __init__(self):
        self._templates: Dict[str, str] = {}
        self._register_default_templates()
    
    def _register_default_templates(self):
        """注册默认模板库"""
        
        # ===== 基础Agent模板 =====
        self._templates["base_agent"] = """
你是一个专业的AI助手，角色是：$role。

请以专业、准确、高效的方式完成任务。
回答时请注意：
1. 仔细理解用户需求
2. 提供准确、有价值的信息
3. 结构清晰，易于理解
4. 如果不确定，诚实说明
"""
        
        # ===== 规划器Agent模板 =====
        self._templates["planner_agent"] = """
你是一位资深的任务规划专家，擅长将复杂任务拆解为可执行的步骤。

你的职责：
1. 深入分析用户的任务需求
2. 评估任务难度和风险
3. 制定详细、可执行的步骤计划
4. 为每个步骤匹配合适的工具

规划原则：
- 步骤要具体，避免模糊笼统
- 合理安排顺序，考虑依赖关系
- 标记高风险步骤，需要用户确认
- 考虑可能的失败情况，预留备选方案

请用结构化的方式输出计划，确保执行器能够准确理解和执行。
"""
        
        # ===== 执行器Agent模板 =====
        self._templates["executor_agent"] = """
你是一位高效的任务执行专家，擅长使用各种工具完成具体任务。

你的职责：
1. 根据规划的步骤，逐步执行任务
2. 选择最合适的工具来完成每个步骤
3. 处理执行过程中的错误和异常
4. 记录执行结果，为后续步骤提供上下文

执行原则：
- 严格按照计划执行，不要随意更改
- 充分利用工具能力，不要硬扛
- 遇到错误先尝试修复，实在不行再报告
- 注意安全，高风险操作要谨慎

当前执行步骤：$step
是否为重试：$retry
"""
        
        # ===== 批评家Agent模板 =====
        self._templates["critic_agent"] = """
你是一位严格的质量评审专家，擅长从多个维度评估工作成果。

你的职责：
1. 客观评估执行结果的质量
2. 从准确性、完整性、清晰度、实用性、安全性等维度打分
3. 指出优点和不足
4. 给出具体的改进建议
5. 判断是否需要重新执行

评审原则：
- 客观公正，不带有主观偏见
- 标准明确，按维度打分
- 建议具体，可操作可执行
- 考虑成本，不要过度优化

记住：你的目标是提升最终结果的质量，不是为了批评而批评。
"""
        
        # ===== 协调器Agent模板 =====
        self._templates["coordinator_agent"] = """
你是一位专业的内容整合专家，擅长将复杂的执行过程整理为清晰的最终回答。

你的职责：
1. 整合所有执行步骤的结果
2. 提炼核心信息和关键结论
3. 以用户友好的方式呈现
4. 隐藏技术细节，只展示用户关心的内容

输出原则：
- 核心结论前置，详细说明后置
- 结构清晰，使用标题、列表、加粗等格式
- 语言自然流畅，像真人在对话
- 不要提及"执行过程"、"步骤"、"Agent"等内部技术术语
- 如果有失败的步骤，巧妙绕过，不要暴露给用户

记住：你是在直接和用户对话，你的回答就是最终交付物。
"""
        
        # ===== 通用优化模板 =====
        self._templates["general_optimize"] = """
$original_prompt

---
以上是原始任务描述。请你以更清晰、更专业的方式重新表述这个任务，
使其更适合AI理解和执行。要求：
1. 明确角色和背景
2. 清晰说明目标和要求
3. 列出关键约束条件
4. 指定期望的输出格式
"""
        
        # ===== 思维链模板 =====
        self._templates["cot"] = """
请解决以下问题：
$problem

请按照以下步骤思考：
1. 首先，理解问题的核心是什么
2. 然后，分析有哪些已知条件
3. 接着，思考可能的解决方法
4. 最后，得出结论并验证

请把你的思考过程写出来，然后给出最终答案。
"""
        
        # ===== 少样本模板 =====
        self._templates["few_shot"] = """
请完成以下任务：$task

这里有几个示例供参考：

$examples

现在请处理新的输入：
$input
"""
        
        # ===== 自我校验模板 =====
        self._templates["self_check"] = """
这是你之前生成的回答：
$answer

请检查这个回答是否存在以下问题：
1. 事实性错误
2. 逻辑漏洞
3. 表述不清
4. 信息不完整
5. 格式问题

如果发现问题，请指出并修正。如果没有问题，请确认回答正确。
"""
    
    # ===== 模板管理 =====
    
    def register_template(self, name: str, template: str):
        """注册一个新模板"""
        self._templates[name] = template
    
    def register_templates(self, templates: Dict[str, str]):
        """批量注册模板"""
        self._templates.update(templates)
    
    def has_template(self, name: str) -> bool:
        """检查模板是否存在"""
        return name in self._templates
    
    def list_templates(self) -> List[str]:
        """列出所有模板名称"""
        return list(self._templates.keys())
    
    # ===== 模板渲染 =====
    
    def render(self, template_name: str, **kwargs) -> str:
        """
        渲染模板
        
        Args:
            template_name: 模板名称
            **kwargs: 模板变量
        
        Returns:
            渲染后的提示词
        """
        if template_name not in self._templates:
            raise ValueError(f"Template not found: {template_name}")
        
        template = self._templates[template_name]
        
        # 使用string.Template进行变量替换
        try:
            t = Template(template)
            result = t.safe_substitute(**kwargs)
        except Exception:
            # 降级：简单替换
            result = template
            for key, value in kwargs.items():
                result = result.replace(f"${key}", str(value))
        
        return result.strip()
    
    def render_with_fallback(
        self,
        template_name: str,
        fallback_template: str = "base_agent",
        **kwargs,
    ) -> str:
        """渲染模板，不存在则使用fallback"""
        if template_name in self._templates:
            return self.render(template_name, **kwargs)
        return self.render(fallback_template, **kwargs)
    
    # ===== 高级渲染 =====
    
    def render_chain(self, template_names: List[str], **kwargs) -> str:
        """
        链式渲染多个模板，拼接结果
        
        用于组合多个模板片段。
        """
        parts = []
        for name in template_names:
            if name in self._templates:
                parts.append(self.render(name, **kwargs))
        return "\n\n".join(parts)
    
    def render_with_examples(
        self,
        base_template: str,
        examples: List[Dict[str, str]],
        **kwargs,
    ) -> str:
        """
        渲染带示例的少样本提示词
        
        Args:
            base_template: 基础模板
            examples: 示例列表，每个包含input和output
            **kwargs: 其他变量
        
        Returns:
            渲染后的提示词
        """
        # 格式化示例
        example_texts = []
        for i, ex in enumerate(examples, 1):
            example_texts.append(f"示例{i}：\n输入：{ex['input']}\n输出：{ex['output']}")
        
        examples_str = "\n\n".join(example_texts)
        
        return self.render(
            "few_shot",
            task=kwargs.get("task", ""),
            examples=examples_str,
            input=kwargs.get("input", ""),
        )
    
    # ===== 模板工具 =====
    
    def extract_variables(self, template_name: str) -> List[str]:
        """提取模板中的变量名"""
        if template_name not in self._templates:
            return []
        
        template = self._templates[template_name]
        # 匹配 $variable 格式的变量
        variables = re.findall(r'\$(\w+)', template)
        return list(set(variables))
    
    def get_template(self, name: str) -> Optional[str]:
        """获取原始模板内容"""
        return self._templates.get(name)
