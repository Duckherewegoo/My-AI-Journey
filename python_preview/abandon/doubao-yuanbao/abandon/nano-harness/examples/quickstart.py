"""
快速上手示例
=============
演示如何使用NanoHarness的核心功能。

运行方式：
    python examples/quickstart.py
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def example_1_basic_concept():
    """示例1：核心概念介绍"""
    print("=" * 60)
    print("示例1：NanoHarness 核心概念")
    print("=" * 60)
    print()
    
    print("NanoHarness 是一个轻量级多智能体编排框架，核心概念包括：")
    print()
    print("1. 🤖 多智能体协作")
    print("   - Planner（规划器）：拆解任务，制定执行计划")
    print("   - Executor（执行器）：逐步执行计划")
    print("   - Critic（批评家）：评审结果，提出改进建议")
    print("   - Coordinator（协调器）：汇总结果，输出最终答案")
    print()
    print("2. 🔌 Function Calling")
    print("   - 基于LangChain的工具调用机制")
    print("   - 支持动态加载和注册工具")
    print("   - 自动参数解析和验证")
    print()
    print("3. 🔗 MCP 协议")
    print("   - 服务端：将系统能力暴露为MCP服务")
    print("   - 客户端：连接外部MCP服务，使用其工具")
    print("   - 双向转换：LangChain ↔ MCP 工具互转")
    print()
    print("4. 🧩 Skill 插件系统")
    print("   - 可插拔的技能包")
    print("   - 内置：Bash、图片、视频、音频、文件")
    print("   - 支持自定义Skill开发")
    print()
    print("5. 💬 提示词工程")
    print("   - 模板引擎：预设9种模板")
    print("   - 优化器：自动优化提示词")
    print("   - 支持少样本、思维链等技巧")
    print()
    print("6. 🖼️ 多模态处理")
    print("   - 图片：描述、OCR、分析")
    print("   - 视频：信息查询、帧提取、摘要")
    print("   - 音频：语音转文字、特征分析")
    print()
    print("7. 💻 Bash 命令执行")
    print("   - 风险等级自动评估")
    print("   - 用户确认机制")
    print("   - 命令黑名单保护")
    print("   - 超时和输出限制")
    print()


def example_2_skill_system():
    """示例2：Skill系统使用"""
    print("=" * 60)
    print("示例2：Skill 插件系统")
    print("=" * 60)
    print()
    
    from nano_harness.skills import SkillRegistry
    from nano_harness.skills.builtin import BashSkill, FileSkill
    
    # 创建注册中心
    registry = SkillRegistry()
    
    # 注册Skill
    bash_skill = BashSkill(work_dir="./workspace")
    file_skill = FileSkill(work_dir="./workspace")
    
    registry.register(bash_skill)
    registry.register(file_skill)
    
    print(f"已注册 {len(registry.get_skill_names())} 个Skill:")
    for name in registry.get_skill_names():
        skill = registry.get_skill(name)
        tools = skill.get_tools()
        print(f"  - {name}: {len(tools)} 个工具")
        for tool in tools:
            print(f"      * {tool.name}")
    print()
    
    # 获取所有工具
    all_tools = registry.get_all_tools()
    print(f"总共 {len(all_tools)} 个可用工具")
    print()
    
    # 搜索Skill
    print("搜索 'file' 相关的Skill:")
    results = registry.search_skills("file")
    for skill in results:
        print(f"  - {skill.name}: {skill.description}")
    print()


def example_3_prompt_engineering():
    """示例3：提示词工程"""
    print("=" * 60)
    print("示例3：提示词工程")
    print("=" * 60)
    print()
    
    from nano_harness.prompts import PromptTemplateEngine, PromptOptimizer
    
    # 模板引擎
    engine = PromptTemplateEngine()
    
    print("可用模板:")
    templates = [
        "base_agent", "planner_agent", "executor_agent",
        "critic_agent", "coordinator_agent", "general_optimize",
        "cot", "few_shot", "self_check"
    ]
    for t in templates:
        print(f"  - {t}")
    print()
    
    # 渲染模板
    rendered = engine.render("base_agent", role="助手", task="回答问题")
    print("base_agent 模板预览（前200字）:")
    print(rendered[:200] + "...")
    print()
    
    # 提示词优化器
    optimizer = PromptOptimizer()
    
    # 优化提示词
    original_prompt = "写一个Python脚本"
    optimized = optimizer.optimize(
        original_prompt,
        task_type="coding",
        add_cot=True,
        add_self_check=True,
    )
    
    print("优化前:")
    print(f"  {original_prompt}")
    print()
    print("优化后（coding类型 + CoT + SelfCheck）:")
    print(optimized[:300] + "...")
    print()
    
    # 分析提示词
    analysis = optimizer.analyze_prompt(optimized)
    print("提示词分析:")
    print(f"  长度: {analysis['length']} 字符")
    print(f"  清晰度评分: {analysis['clarity_score']}/100")
    print(f"  有角色设定: {analysis['has_role']}")
    print(f"  有步骤引导: {analysis['has_steps']}")
    print(f"  有格式要求: {analysis['has_format']}")
    print()


def example_4_bash_security():
    """示例4：Bash安全机制"""
    print("=" * 60)
    print("示例4：Bash 命令安全机制")
    print("=" * 60)
    print()
    
    from nano_harness.skills.builtin import BashSkill
    
    # 创建BashSkill
    bash = BashSkill(
        work_dir="./workspace",
        auto_confirm_low_risk=True,
    )
    
    # 测试不同风险等级的命令
    test_commands = [
        "ls -la",
        "echo hello world",
        "mkdir test_dir",
        "rm -rf /",
        "sudo apt-get install vim",
    ]
    
    print("命令风险评估:")
    for cmd in test_commands:
        risk = bash._assess_risk(cmd)
        forbidden = bash._is_forbidden(cmd)
        status = "❌ 禁止" if forbidden else f"⚠️  {risk}"
        print(f"  {status:10} | {cmd}")
    print()
    
    print("安全特性:")
    print("  ✅ 风险等级自动评估（low/medium/high/forbidden）")
    print("  ✅ 用户确认回调（高风险命令需用户确认）")
    print("  ✅ 命令黑名单（禁止极度危险的命令）")
    print("  ✅ 工作目录限制（防止路径穿越）")
    print("  ✅ 输出长度限制（防止输出过大）")
    print("  ✅ 超时控制（防止命令卡死）")
    print("  ✅ 命令历史记录")
    print()


def example_5_mcp_protocol():
    """示例5：MCP协议"""
    print("=" * 60)
    print("示例5：MCP 协议支持")
    print("=" * 60)
    print()
    
    from nano_harness.mcp.server import MCPServer
    from nano_harness.mcp.client import MCPClient
    from nano_harness.mcp.tools import MCPToolAdapter
    
    print("MCP 服务端能力:")
    print("  ✅ Tools - 工具注册和调用")
    print("  ✅ Resources - 资源读取")
    print("  ✅ Prompts - 提示词模板")
    print("  ✅ JSON-RPC 2.0 协议")
    print("  ✅ stdio 传输模式")
    print("  ✅ 可与LangChain桥接")
    print()
    
    print("MCP 客户端能力:")
    print("  ✅ 连接本地MCP服务（stdio）")
    print("  ✅ 连接远程MCP服务（HTTP）")
    print("  ✅ 列出和调用工具")
    print("  ✅ 自动转换为LangChain工具")
    print()
    
    print("MCP 工具适配器:")
    print("  ✅ LangChain → MCP 转换")
    print("  ✅ MCP → LangChain 转换")
    print("  ✅ Skill一键暴露为MCP服务")
    print("  ✅ 从MCP服务导入工具到Skill注册中心")
    print()
    
    print("使用场景:")
    print("  1. 将NanoHarness作为MCP服务，供其他AI客户端调用")
    print("  2. 接入外部MCP服务，扩展系统能力")
    print("  3. 与Claude Desktop、Cursor等支持MCP的工具集成")
    print()


def example_6_multimodal():
    """示例6：多模态处理"""
    print("=" * 60)
    print("示例6：多模态处理")
    print("=" * 60)
    print()
    
    from nano_harness.multimodal.image import ImageProcessor
    from nano_harness.multimodal.video import VideoProcessor
    from nano_harness.multimodal.audio import AudioProcessor
    
    print("图片处理 (ImageProcessor):")
    print("  - describe(): 描述图片内容")
    print("  - extract_text(): OCR文字提取")
    print("  - analyze(): 综合分析")
    print("  - get_image_info(): 基本信息")
    print("  - batch_describe(): 批量处理")
    print()
    
    print("视频处理 (VideoProcessor):")
    print("  - get_info(): 视频基本信息")
    print("  - extract_frames(): 提取帧")
    print("  - summarize(): 视频摘要")
    print("  - detect_scenes(): 场景检测")
    print("  - extract_audio(): 提取音频")
    print()
    
    print("音频处理 (AudioProcessor):")
    print("  - get_info(): 音频基本信息")
    print("  - transcribe(): 语音转文字")
    print("  - analyze(): 综合分析")
    print("  - convert_format(): 格式转换")
    print("  - split_audio(): 分割音频")
    print("  - detect_silence(): 静音检测")
    print()
    
    print("设计原则:")
    print("  ✅ 多后端支持（优先专业库，自动降级）")
    print("  ✅ 统一的接口风格")
    print("  ✅ 优雅降级（缺少依赖时不崩溃）")
    print("  ✅ 可配置的模型/参数")
    print()


def example_7_api_server():
    """示例7：REST API"""
    print("=" * 60)
    print("示例7：REST API 服务")
    print("=" * 60)
    print()
    
    print("API 端点:")
    print()
    print("对话接口:")
    print("  POST /api/v1/chat          - 发送消息，获取回复")
    print("  WS   /ws/chat              - WebSocket实时对话")
    print()
    print("任务接口:")
    print("  POST /api/v1/tasks         - 创建任务")
    print("  GET  /api/v1/tasks/{id}    - 查询任务状态")
    print("  GET  /api/v1/tasks         - 列出任务")
    print()
    print("Skill接口:")
    print("  GET  /api/v1/skills        - 列出所有Skill")
    print("  GET  /api/v1/skills/{name} - 获取Skill详情")
    print()
    print("MCP接口:")
    print("  GET  /api/v1/mcp/tools     - 列出MCP工具")
    print("  POST /api/v1/mcp/call      - 调用MCP工具")
    print()
    print("其他:")
    print("  GET  /                     - API信息")
    print("  GET  /health               - 健康检查")
    print("  GET  /ui                   - Web界面")
    print()
    print("启动方式:")
    print("  python main.py             # 默认启动")
    print("  python main.py --port 8080 # 指定端口")
    print()


def main():
    """运行所有示例"""
    examples = [
        ("核心概念", example_1_basic_concept),
        ("Skill系统", example_2_skill_system),
        ("提示词工程", example_3_prompt_engineering),
        ("Bash安全机制", example_4_bash_security),
        ("MCP协议", example_5_mcp_protocol),
        ("多模态处理", example_6_multimodal),
        ("REST API", example_7_api_server),
    ]
    
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "NanoHarness 快速上手" + " " * 22 + "║")
    print("╚" + "═" * 58 + "╝")
    print()
    
    for i, (name, func) in enumerate(examples, 1):
        try:
            func()
        except Exception as e:
            print(f"❌ 示例 {i} 执行出错: {e}")
            import traceback
            traceback.print_exc()
        
        if i < len(examples):
            input("\n按回车继续下一个示例...")
            print()
    
    print("=" * 60)
    print("  ✅ 所有示例完成！")
    print("=" * 60)
    print()
    print("下一步:")
    print("  1. 配置 LLM API Key")
    print("  2. 运行 python main.py 启动服务")
    print("  3. 访问 http://localhost:8000/ui 使用Web界面")
    print()


if __name__ == "__main__":
    main()
