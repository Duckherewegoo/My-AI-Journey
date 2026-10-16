"""
写作智能体
负责根据研究素材撰写文章草稿
"""

from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent, AgentState


class WriterAgent(BaseAgent):
    """
    写作智能体
    负责根据研究素材撰写高质量的文章草稿
    """

    def __init__(
        self,
        llm: BaseChatModel,
        name: str = "写作专家",
        description: str = "专业的作家，擅长撰写各种类型的文章，文笔优美，逻辑清晰",
        system_prompt: str = None,
    ):
        """
        初始化写作智能体

        Args:
            llm: 语言模型实例
            name: 智能体名称
            description: 智能体描述
            system_prompt: 系统提示词
        """
        default_prompt = """你是一位资深的写作专家，拥有出色的文字表达能力。
你的任务是根据提供的研究素材，撰写一篇结构完整、内容丰富的文章。

请遵循以下写作原则：
1. 结构清晰：文章要有明确的开头、主体和结尾
2. 逻辑严密：段落之间要有自然的过渡和衔接
3. 内容充实：要有具体的例子和数据支撑观点
4. 语言流畅：用词准确，句子通顺
5. 深度思考：不仅陈述事实，还要有分析和见解
6. 读者友好：考虑读者的阅读体验，易于理解

请输出完整的文章内容，包括标题和各个章节。"""

        super().__init__(
            llm=llm,
            name=name,
            description=description,
            system_prompt=system_prompt or default_prompt,
        )

    async def run(self, state: AgentState) -> AgentState:
        """
        执行写作任务

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        # 构建研究素材
        research_notes_str = "\n".join(
            [f"{i+1}. {note}" for i, note in enumerate(state.research_notes)]
        )

        # 构建写作提示
        writing_prompt = f"""请根据以下研究素材，撰写一篇关于"{state.topic}"的文章：

研究素材：
{research_notes_str}

文章要求：
1. 字数不少于800字
2. 包含一个吸引人的标题
3. 分为多个章节，每个章节有明确的小标题
4. 开头要有引言，结尾要有总结
5. 语言要专业但不晦涩
6. 要有自己的分析和见解

请直接输出完整的文章内容。"""

        # 如果有审核反馈，需要根据反馈修改
        if state.review_feedback and state.iteration_count > 1:
            writing_prompt += f"""

注意：这是第{state.iteration_count}次修改，请根据以下审核反馈进行修改：
{state.review_feedback}

请在保持文章原有优点的基础上，针对反馈意见进行改进。"""

        # 构建上下文
        context = {
            "当前迭代次数": state.iteration_count,
            "研究笔记数量": len(state.research_notes),
            "是否有审核反馈": bool(state.review_feedback),
        }

        # 调用LLM进行写作
        messages = self._build_messages(writing_prompt, context)
        response = await self._call_llm(messages)

        # 更新状态
        state.draft_content = response
        state.current_step = "review"
        state.metadata["writer_agent_output"] = response

        return state
