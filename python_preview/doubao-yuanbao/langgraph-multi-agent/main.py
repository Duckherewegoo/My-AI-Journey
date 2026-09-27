"""
多智能体协作写作系统 - 主程序
提供Gradio Web界面，用户可以输入主题，系统自动完成研究、写作、审核、编辑全流程
"""

import os
import asyncio
from typing import Dict, Any, Optional
import gradio as gr
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from graph.workflow import create_workflow, create_initial_state, WorkflowConfig
from utils.helpers import (
    format_research_notes,
    count_words,
    extract_title,
    generate_summary,
    save_to_file,
    get_timestamp,
    ensure_directory,
)

# 加载环境变量
load_dotenv()


class MultiAgentWritingSystem:
    """
    多智能体协作写作系统
    整合研究、写作、审核、编辑四个智能体，完成完整的写作流程
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化系统

        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.llm = self._init_llm()
        self.workflow = self._init_workflow()
        self.output_dir = self.config.get("output_dir", "outputs")
        ensure_directory(self.output_dir)

    def _init_llm(self) -> ChatOpenAI:
        """
        初始化语言模型

        Returns:
            语言模型实例
        """
        llm_config = self.config.get("llm", {})
        model = llm_config.get("model", "qwen-plus")
        temperature = llm_config.get("temperature", 0.7)
        api_key = llm_config.get("api_key") or os.getenv("OPENAI_API_KEY")
        base_url = llm_config.get("base_url") or os.getenv("OPENAI_BASE_URL")

        kwargs = {
            "model": model,
            "temperature": temperature,
        }

        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url

        return ChatOpenAI(**kwargs)

    def _init_workflow(self):
        """
        初始化工作流

        Returns:
            编译后的工作流
        """
        workflow_config = WorkflowConfig(
            llm=self.llm,
            max_iterations=self.config.get("max_iterations", 3),
            researcher_config=self.config.get("researcher"),
            writer_config=self.config.get("writer"),
            reviewer_config=self.config.get("reviewer"),
            editor_config=self.config.get("editor"),
        )

        return create_workflow(workflow_config)

    async def run_writing_task(
        self,
        topic: str,
        max_iterations: int = 3,
        progress_callback=None,
    ) -> Dict[str, Any]:
        """
        运行写作任务

        Args:
            topic: 写作主题
            max_iterations: 最大迭代次数
            progress_callback: 进度回调函数

        Returns:
            最终结果字典
        """
        # 创建初始状态
        initial_state = create_initial_state(
            topic=topic,
            max_iterations=max_iterations,
        )

        # 记录每一步的状态
        steps = []

        def step_callback(state):
            """步骤回调"""
            current_step = state.get("current_step", "unknown")
            steps.append(state.copy())

            if progress_callback:
                progress_info = {
                    "step": current_step,
                    "iteration": state.get("iteration_count", 0),
                    "total_steps": max_iterations + 2,  # research + write*n + review*n + edit
                }
                asyncio.create_task(progress_callback(progress_info))

        # 运行工作流
        final_state = await self.workflow.ainvoke(initial_state)

        # 保存结果
        self._save_result(final_state)

        return {
            "topic": topic,
            "final_content": final_state.get("final_content", ""),
            "draft_content": final_state.get("draft_content", ""),
            "research_notes": final_state.get("research_notes", []),
            "review_feedback": final_state.get("review_feedback", ""),
            "iteration_count": final_state.get("iteration_count", 0),
            "metadata": final_state.get("metadata", {}),
        }

    def _save_result(self, state: Dict[str, Any]) -> str:
        """
        保存结果到文件

        Args:
            state: 最终状态

        Returns:
            保存的文件路径
        """
        topic = state.get("topic", "untitled")
        timestamp = get_timestamp()

        # 保存最终文章
        final_content = state.get("final_content", "")
        if final_content:
            filename = f"final_{timestamp}.md"
            filepath = os.path.join(self.output_dir, filename)
            save_to_file(final_content, filepath)

        # 保存完整状态
        state_filename = f"state_{timestamp}.json"
        state_filepath = os.path.join(self.output_dir, state_filename)

        import json
        serializable_state = {}
        for key, value in state.items():
            if isinstance(value, (str, int, float, bool, list, dict, type(None))):
                serializable_state[key] = value
            else:
                serializable_state[key] = str(value)

        with open(state_filepath, 'w', encoding='utf-8') as f:
            json.dump(serializable_state, f, ensure_ascii=False, indent=2)

        return state_filepath


def create_gradio_interface(system: MultiAgentWritingSystem):
    """
    创建Gradio界面

    Args:
        system: 多智能体写作系统实例

    Returns:
        Gradio界面
    """

    async def generate_article(
        topic: str,
        model: str,
        temperature: float,
        max_iterations: int,
        api_key: str,
        base_url: str,
        progress=gr.Progress(),
    ):
        """
        生成文章

        Args:
            topic: 写作主题
            model: 模型名称
            temperature: 温度
            max_iterations: 最大迭代次数
            api_key: API密钥
            base_url: API基础URL
            progress: 进度条

        Returns:
            生成结果
        """
        if not topic.strip():
            raise gr.Error("请输入写作主题")

        # 更新配置
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        if base_url:
            os.environ["OPENAI_BASE_URL"] = base_url

        # 重新初始化LLM
        system.config["llm"] = {
            "model": model,
            "temperature": temperature,
        }
        system.llm = system._init_llm()
        system.workflow = system._init_workflow()

        # 进度跟踪
        progress(0.1, desc="正在初始化...")

        # 运行写作任务
        result = await system.run_writing_task(
            topic=topic,
            max_iterations=max_iterations,
        )

        progress(1.0, desc="完成！")

        # 格式化输出
        research_notes_str = format_research_notes(result["research_notes"])
        word_count = count_words(result["final_content"])
        title = extract_title(result["final_content"]) or topic

        return (
            result["final_content"],
            research_notes_str,
            result["review_feedback"],
            f"标题：{title}\n字数：{word_count}字\n迭代次数：{result['iteration_count']}次",
        )

    # 创建界面
    with gr.Blocks(
        title="多智能体协作写作系统"
        # theme=gr.themes.Soft(),
    ) as demo:
        gr.Markdown(
            """
            # 🤖 多智能体协作写作系统

            基于 LangGraph + LangChain + Gradio 构建的多智能体协作写作平台。
            系统包含**研究专家**、**写作专家**、**审核专家**、**总编辑**四个智能体，
            自动完成从资料收集到最终润色的完整写作流程。

            ## 工作流程
            1. **研究阶段**：收集主题相关的信息和素材
            2. **写作阶段**：根据研究素材撰写文章草稿
            3. **审核阶段**：对文章进行多维度审核，提供修改建议
            4. **编辑阶段**：对文章进行最终润色和优化

            *审核不通过时会自动返回写作阶段进行修改，最多迭代指定次数*
            """
        )

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 配置")

                topic_input = gr.Textbox(
                    label="写作主题",
                    placeholder="请输入你想写的主题，例如：人工智能的未来发展",
                    lines=3,
                )

                with gr.Accordion("高级设置", open=False):
                    model_select = gr.Dropdown(
                        label="通义千问模型",
                        choices=[
                            "qwen-turbo",
                            "qwen-plus",
                            "qwen-max",
                            "qwen-long",
                        ],
                        value="qwen-turbo",
                    )

                    temperature_slider = gr.Slider(
                        label="创造性 (Temperature)",
                        minimum=0.0,
                        maximum=1.0,
                        value=0.7,
                        step=0.1,
                    )

                    max_iterations_slider = gr.Slider(
                        label="最大迭代次数",
                        minimum=1,
                        maximum=5,
                        value=3,
                        step=1,
                    )

                    api_key_input = gr.Textbox(
                        label="DashScope API Key",
                        type="password",
                        placeholder="sk-...",
                    )

                    base_url_input = gr.Textbox(
                        label="API Base URL",
                        placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    )

                generate_btn = gr.Button(
                    "🚀 开始写作",
                    variant="primary",
                    size="lg",
                )

            with gr.Column(scale=2):
                gr.Markdown("### 📝 输出结果")

                with gr.Tabs():
                    with gr.Tab("最终文章"):
                        final_output = gr.Markdown(
                            label="最终文章",
                            value="*点击「开始写作」按钮生成文章*",
                        )

                    with gr.Tab("研究笔记"):
                        research_output = gr.Markdown(
                            label="研究笔记",
                            value="*研究笔记将显示在这里*",
                        )

                    with gr.Tab("审核反馈"):
                        review_output = gr.Markdown(
                            label="审核反馈",
                            value="*审核反馈将显示在这里*",
                        )

                info_output = gr.Markdown(
                    label="统计信息",
                    value="",
                )

        # 示例
        gr.Examples(
            examples=[
                ["人工智能对未来教育的影响", "qwen-turbo", 0.7, 3, "", ""],
                ["远程工作的优缺点分析", "qwen-turbo", 0.6, 2, "", ""],
                ["如何培养良好的阅读习惯", "qwen-turbo", 0.8, 3, "", ""],
            ],
            inputs=[
                topic_input,
                model_select,
                temperature_slider,
                max_iterations_slider,
                api_key_input,
                base_url_input,
            ],
        )

        # 绑定事件
        generate_btn.click(
            fn=generate_article,
            inputs=[
                topic_input,
                model_select,
                temperature_slider,
                max_iterations_slider,
                api_key_input,
                base_url_input,
            ],
            outputs=[
                final_output,
                research_output,
                review_output,
                info_output,
            ],
        )

        gr.Markdown(
            """
            ---
            **技术栈**：LangGraph · LangChain · Gradio · Python 3.10+

            *本系统需要配置 DashScope API Key 才能正常运行*
            """
        )

    return demo


def main():
    """主函数"""
    # 创建系统实例
    system = MultiAgentWritingSystem()

    # 创建Gradio界面
    demo = create_gradio_interface(system)

    # 启动服务
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        # share=False,
        debug=False,
        show_error=True
        # stream_output=False,  # 强制关闭流式输出
        # auto_reload=False     # 关闭自动重载
    )


if __name__ == "__main__":
    main()
