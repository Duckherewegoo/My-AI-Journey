"""
提示词工程包
=============
提示词模板引擎和优化器。

包含：
- 模板引擎：管理和渲染各种提示词模板
- 优化器：自动优化提示词质量
- 预设模板：各种场景的高质量提示词

提示词工程小技巧：
1. 角色设定：给AI明确的身份和专业背景
2. 任务拆解：把复杂任务拆成步骤
3. 输出格式：明确指定输出格式
4. 思维链：引导AI逐步思考
5. 少样本：提供示例引导
6. 自我校验：让AI检查自己的输出
"""

from .templates import PromptTemplateEngine
from .optimizer import PromptOptimizer

__all__ = ["PromptTemplateEngine", "PromptOptimizer"]
