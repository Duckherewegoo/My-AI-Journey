"""
编辑智能体
负责对文章进行最终编辑和润色，确保文章质量
"""

from langchain_core.language_models import BaseChatModel
from .base_agent import BaseAgent, AgentState


class EditorAgent(BaseAgent):
    """
    编辑智能体
    负责对文章进行最终编辑和润色，提升文章的整体质量
    """

    def __init__(
        self,
        llm: BaseChatModel,
        name: str = "总编辑",
        description: str = "资深总编辑，擅长文章润色和优化，确保文章达到出版级别",
        system_prompt: str = None,
    ):
        """
        初始化编辑智能体

        Args:
            llm: 语言模型实例
            name: 智能体名称
            description: 智能体描述
            system_prompt: 系统提示词
        """
        default_prompt = """你是一位资深的总编辑，拥有丰富的编辑经验和出色的文字功底。
你的任务是对文章进行最终的编辑和润色，确保文章达到出版级别的质量。

请从以下方面进行编辑优化：
1. 标题优化：让标题更加吸引人、准确传达文章核心
2. 语言润色：优化用词和句式，让文章更加流畅优美
3. 结构调整：优化段落结构和顺序，提升逻辑连贯性
4. 细节完善：修正错别字、标点符号、格式等问题
5. 风格统一：确保全文风格一致，符合目标读者
6. 价值提升：在不改变原意的基础上，提升文章的深度和价值

请保持文章的核心内容和观点不变，主要进行语言和形式上的优化。
输出最终的文章版本，不要包含编辑过程或说明。"""

        super().__init__(
            llm=llm,
            name=name,
            description=description,
            system_prompt=system_prompt or default_prompt,
        )

    async def run(self, state: AgentState) -> AgentState:
        """
        执行编辑任务

        Args:
            state: 当前状态

        Returns:
            更新后的状态
        """
        # 构建编辑提示
        editing_prompt = f"""请对以下关于"{state.topic}"的文章进行最终编辑和润色：

文章内容：
{state.draft_content}

请进行以下优化：
1. 优化标题，让它更吸引人
2. 润色语言，让表达更流畅优美
3. 调整结构，让逻辑更清晰
4. 修正所有细节问题（错别字、标点、格式等）
5. 统一文章风格
6. 提升整体质量

请保持文章的核心内容和观点不变，只进行形式上的优化。
直接输出最终的文章版本，不要包含任何编辑说明。"""

        # 构建上下文
        context = {
            "当前迭代次数": state.iteration_count,
            "文章字数": len(state.draft_content),
            "是否经过审核": bool(state.review_feedback),
        }

        # 调用LLM进行编辑
        messages = self._build_messages(editing_prompt, context)
        response = await self._call_llm(messages)

        # 更新状态
        state.final_content = response
        state.current_step = "done"
        state.metadata["editor_agent_output"] = response

        return state
