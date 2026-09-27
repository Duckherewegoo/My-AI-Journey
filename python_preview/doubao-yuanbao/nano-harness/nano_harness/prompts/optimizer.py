"""
提示词优化器
=============
自动优化提示词质量的工具。

提示词工程小技巧合集：
1. 角色强化：给AI更具体的身份设定
2. 任务拆解：把复杂任务拆成明确步骤
3. 输出规范：明确指定输出格式
4. 思维链引导：引导AI逐步思考
5. 约束条件：明确列出限制和要求
6. 质量标准：说明什么样的结果算好
7. 示例引导：提供参考示例
8. 自我校验：让AI检查自己的输出
"""

import re
from typing import Dict, List, Optional


class PromptOptimizer:
    """
    提示词优化器
    
    自动分析和优化提示词，提升AI输出质量。
    
    优化策略：
    - 角色注入：自动添加专业角色设定
    - 结构增强：添加步骤引导
    - 格式规范：明确输出格式
    - 质量要求：添加质量标准
    - 约束补充：补充常见约束条件
    """
    
    # 不同任务类型的优化策略
    TASK_STRATEGIES = {
        "general": {
            "role": "你是一位专业、高效的AI助手",
            "quality": "请确保回答准确、清晰、有价值",
            "format": "请用清晰的结构组织你的回答",
        },
        "coding": {
            "role": "你是一位资深软件工程师，精通多种编程语言和最佳实践",
            "quality": "代码要健壮、高效、有良好的注释和错误处理",
            "format": "请先说明思路，再给出代码，最后解释关键部分",
        },
        "writing": {
            "role": "你是一位专业作家，擅长各种文体的创作",
            "quality": "内容要生动、有深度、语言流畅自然",
            "format": "注意段落结构和逻辑层次",
        },
        "analysis": {
            "role": "你是一位资深分析师，擅长从复杂信息中提炼洞察",
            "quality": "分析要客观、全面、有数据支撑",
            "format": "请分点列出分析结果，结论前置",
        },
        "creative": {
            "role": "你是一位富有创意的艺术家，想象力丰富",
            "quality": "创意要新颖、独特、有感染力",
            "format": "尽情发挥你的创造力",
        },
        "technical": {
            "role": "你是一位技术专家，对技术原理有深入理解",
            "quality": "技术解释要准确、严谨、有深度",
            "format": "由浅入深，先讲概念再讲细节",
        },
    }
    
    def __init__(self):
        self._custom_strategies: Dict[str, Dict] = {}
    
    def register_strategy(self, task_type: str, strategy: Dict):
        """注册自定义优化策略"""
        self._custom_strategies[task_type] = strategy
    
    def optimize(
        self,
        prompt: str,
        task_type: str = "general",
        add_cot: bool = False,
        add_self_check: bool = False,
    ) -> str:
        """
        优化提示词
        
        Args:
            prompt: 原始提示词
            task_type: 任务类型
            add_cot: 是否添加思维链引导
            add_self_check: 是否添加自我校验
        
        Returns:
            优化后的提示词
        """
        # 获取策略
        strategy = self._get_strategy(task_type)
        
        parts = []
        
        # 1. 角色设定
        parts.append(f"【角色设定】\n{strategy['role']}")
        
        # 2. 任务描述（原始提示词）
        parts.append(f"【任务】\n{prompt}")
        
        # 3. 质量要求
        parts.append(f"【质量要求】\n{strategy['quality']}")
        
        # 4. 输出格式
        parts.append(f"【输出要求】\n{strategy['format']}")
        
        # 5. 思维链（可选）
        if add_cot:
            parts.append("""
【思考步骤】
请按以下步骤思考：
1. 先理解问题的核心和背景
2. 分析关键要点和约束条件
3. 考虑可能的方案和它们的优缺点
4. 选择最佳方案并组织成清晰的回答
5. 最后检查一下是否有遗漏或错误
""")
        
        # 6. 自我校验（可选）
        if add_self_check:
            parts.append("""
【自我校验】
在给出最终回答前，请检查：
1. 是否准确理解了问题？
2. 回答是否完整覆盖了所有要点？
3. 是否存在事实性错误？
4. 逻辑是否清晰合理？
5. 表达是否清晰易懂？
""")
        
        # 7. 结尾鼓励
        parts.append("现在请开始你的工作。")
        
        return "\n\n".join(parts)
    
    def _get_strategy(self, task_type: str) -> Dict:
        """获取优化策略"""
        if task_type in self._custom_strategies:
            return self._custom_strategies[task_type]
        return self.TASK_STRATEGIES.get(task_type, self.TASK_STRATEGIES["general"])
    
    # ===== 高级优化技巧 =====
    
    def add_role_play(self, prompt: str, role: str) -> str:
        """添加角色扮演设定"""
        return f"请你扮演{role}。\n\n{prompt}"
    
    def add_step_by_step(self, prompt: str, steps: List[str]) -> str:
        """添加步骤引导"""
        steps_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
        return f"{prompt}\n\n请按以下步骤进行：\n{steps_text}"
    
    def add_output_format(self, prompt: str, format_desc: str) -> str:
        """明确输出格式"""
        return f"{prompt}\n\n输出格式要求：{format_desc}"
    
    def add_constraints(self, prompt: str, constraints: List[str]) -> str:
        """添加约束条件"""
        constraints_text = "\n".join(f"- {c}" for c in constraints)
        return f"{prompt}\n\n注意事项：\n{constraints_text}"
    
    def add_examples(self, prompt: str, examples: List[Dict[str, str]]) -> str:
        """添加示例（少样本学习）"""
        example_texts = []
        for i, ex in enumerate(examples, 1):
            example_texts.append(f"示例{i}：\n输入：{ex['input']}\n输出：{ex['output']}")
        
        examples_str = "\n\n".join(example_texts)
        return f"{prompt}\n\n参考示例：\n{examples_str}"
    
    # ===== 提示词分析 =====
    
    def analyze_prompt(self, prompt: str) -> Dict:
        """
        分析提示词质量
        
        返回分析报告，包括：
        - 长度评估
        - 结构完整性
        - 明确程度
        - 改进建议
        """
        analysis = {
            "length": len(prompt),
            "has_role": False,
            "has_steps": False,
            "has_format": False,
            "has_constraints": False,
            "clarity_score": 0,
            "suggestions": [],
        }
        
        # 检查角色设定
        role_keywords = ["你是", "请扮演", "作为", "role", "角色"]
        if any(kw in prompt for kw in role_keywords):
            analysis["has_role"] = True
            analysis["clarity_score"] += 20
        else:
            analysis["suggestions"].append("建议添加角色设定，让AI更有代入感")
        
        # 检查步骤引导
        step_keywords = ["步骤", "第一步", "首先", "step", "1.", "2."]
        if any(kw in prompt for kw in step_keywords):
            analysis["has_steps"] = True
            analysis["clarity_score"] += 20
        else:
            analysis["suggestions"].append("复杂任务建议添加步骤引导，提升结果质量")
        
        # 检查输出格式
        format_keywords = ["格式", "输出", "请按", "JSON", "列表", "表格"]
        if any(kw in prompt for kw in format_keywords):
            analysis["has_format"] = True
            analysis["clarity_score"] += 20
        else:
            analysis["suggestions"].append("建议明确输出格式，让结果更符合预期")
        
        # 检查约束条件
        constraint_keywords = ["注意", "不要", "必须", "限制", "约束", "不能"]
        if any(kw in prompt for kw in constraint_keywords):
            analysis["has_constraints"] = True
            analysis["clarity_score"] += 20
        else:
            analysis["suggestions"].append("可以补充一些约束条件，避免AI跑偏")
        
        # 长度评估
        if len(prompt) < 50:
            analysis["suggestions"].append("提示词偏短，可能不够明确，建议补充细节")
        elif len(prompt) > 2000:
            analysis["suggestions"].append("提示词偏长，可能有冗余信息，建议精简")
        else:
            analysis["clarity_score"] += 20
        
        # 确保分数不超过100
        analysis["clarity_score"] = min(analysis["clarity_score"], 100)
        
        return analysis
    
    def detect_task_type(self, prompt: str) -> str:
        """自动检测任务类型"""
        prompt_lower = prompt.lower()
        
        # 编码任务
        coding_keywords = ["代码", "编程", "函数", "bug", "python", "java", "javascript", "写个", "实现"]
        if any(kw in prompt_lower for kw in coding_keywords):
            return "coding"
        
        # 写作任务
        writing_keywords = ["写一篇", "文章", "作文", "故事", "小说", "文案", "报告"]
        if any(kw in prompt_lower for kw in writing_keywords):
            return "writing"
        
        # 分析任务
        analysis_keywords = ["分析", "研究", "对比", "评估", "总结", "归纳"]
        if any(kw in prompt_lower for kw in analysis_keywords):
            return "analysis"
        
        # 创意任务
        creative_keywords = ["创意", "设计", "想象", "如果", "假如", "灵感"]
        if any(kw in prompt_lower for kw in creative_keywords):
            return "creative"
        
        # 技术任务
        technical_keywords = ["原理", "机制", "架构", "算法", "技术", "怎么实现"]
        if any(kw in prompt_lower for kw in technical_keywords):
            return "technical"
        
        return "general"
