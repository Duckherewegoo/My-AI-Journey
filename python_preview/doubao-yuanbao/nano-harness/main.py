#!/usr/bin/env python3
"""
NanoHarness - 入口文件
=======================
启动NanoHarness系统的主入口。

用法：
    python main.py              # 启动API服务
    python main.py --cli        # 命令行交互模式
    python main.py --demo       # 演示模式
"""

import os
import sys
import argparse


def main():
    parser = argparse.ArgumentParser(
        description="NanoHarness - 轻量级多智能体编排框架"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="启动命令行交互模式"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="运行演示"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="API服务监听地址"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="API服务监听端口"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径"
    )
    
    args = parser.parse_args()
    
    if args.demo:
        run_demo()
    elif args.cli:
        run_cli()
    else:
        run_server(args.host, args.port)


def run_demo():
    """运行演示"""
    print("=" * 60)
    print("  NanoHarness - 轻量级多智能体编排框架")
    print("=" * 60)
    print()
    
    # 导入核心模块
    try:
        from nano_harness import __version__
        print(f"版本: {__version__}")
    except:
        print("版本: 1.0.0")
    
    print()
    print("📦 核心模块:")
    print("  ✅ Harness 编排引擎")
    print("  ✅ 多智能体（规划/执行/评审/协调）")
    print("  ✅ Function Calling")
    print("  ✅ MCP 协议（服务端+客户端）")
    print("  ✅ Skill 插件系统")
    print("  ✅ 提示词工程（模板+优化器）")
    print("  ✅ 多模态处理（图片/视频/音频）")
    print("  ✅ Bash 命令执行（带用户确认）")
    print("  ✅ REST API + WebSocket")
    print("  ✅ Web 交互界面")
    print()
    
    print("📂 目录结构:")
    print_structure()
    print()
    
    print("🚀 启动方式:")
    print("  python main.py           # 启动API服务")
    print("  python main.py --cli     # 命令行交互")
    print("  python main.py --demo    # 演示模式")
    print()
    
    print("🌐 API 文档:")
    print("  http://localhost:8000/docs")
    print()
    
    print("=" * 60)
    print("  演示完成！运行 python main.py 启动服务")
    print("=" * 60)


def print_structure():
    """打印项目结构"""
    structure = """
    nano-harness/
    ├── nano_harness/
    │   ├── __init__.py
    │   ├── harness.py              # 核心编排引擎
    │   ├── agent/                  # 多智能体
    │   │   ├── base.py
    │   │   ├── planner.py          # 规划器
    │   │   ├── executor.py         # 执行器
    │   │   ├── critic.py           # 批评家
    │   │   └── coordinator.py      # 协调器
    │   ├── mcp/                    # MCP协议
    │   │   ├── server.py
    │   │   ├── client.py
    │   │   └── tools.py
    │   ├── skills/                 # Skill机制
    │   │   ├── base.py
    │   │   ├── registry.py
    │   │   └── builtin/            # 内置Skill
    │   │       ├── bash_skill.py   # Bash执行
    │   │       ├── image_skill.py  # 图片处理
    │   │       ├── video_skill.py  # 视频处理
    │   │       ├── audio_skill.py  # 音频处理
    │   │       └── file_skill.py   # 文件操作
    │   ├── multimodal/             # 多模态
    │   │   ├── image.py
    │   │   ├── video.py
    │   │   └── audio.py
    │   ├── prompts/                # 提示词工程
    │   │   ├── templates.py
    │   │   └── optimizer.py
    │   └── api/                    # REST API
    │       ├── __init__.py
    │       └── server.py
    ├── web/
    │   └── index.html              # Web界面
    ├── examples/
    │   └── quickstart.py           # 快速上手示例
    ├── config.yaml                 # 配置文件
    ├── requirements.txt            # 依赖
    └── README.md                   # 项目文档
    """
    print(structure)


def run_cli():
    """命令行交互模式"""
    print("=" * 60)
    print("  NanoHarness CLI")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 60)
    print()
    
    # 尝试初始化Harness
    harness = None
    try:
        # 这里可以根据配置初始化Harness
        print("ℹ️  提示：配置LLM后可获得完整AI能力")
        print("    当前为演示模式，仅展示系统结构")
        print()
    except Exception as e:
        print(f"⚠️  Harness初始化失败: {e}")
        print("    运行在演示模式")
        print()
    
    while True:
        try:
            user_input = input("你: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break
            
            if user_input.lower() in ['help', '?']:
                print_help()
                continue
            
            # 简单的演示回复
            print()
            print("AI: 这是演示模式。")
            print("    配置LLM并初始化Harness后可获得完整AI能力。")
            print("    支持的功能：多智能体协作、Skill插件、MCP协议、")
            print("    多模态处理、Bash命令执行、REST API等。")
            print()
            
        except KeyboardInterrupt:
            print("\n\n👋 再见！")
            break
        except EOFError:
            print("\n👋 再见！")
            break


def print_help():
    """打印帮助信息"""
    print("""
可用命令:
  help / ?      显示帮助
  quit / exit   退出程序
  status        查看系统状态
  skills        列出可用Skill
  agents        列出Agent信息

直接输入消息与AI对话。
    """)


def run_server(host: str, port: int):
    """启动API服务器"""
    try:
        from nano_harness.api import run_server
        
        print(f"🚀 启动 NanoHarness API 服务...")
        print(f"📡 地址: http://{host}:{port}")
        print(f"📚 文档: http://{host}:{port}/docs")
        print(f"🌐 界面: http://{host}:{port}/ui")
        print()
        print("按 Ctrl+C 停止服务")
        print()
        
        run_server(host=host, port=port)
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("    请先安装依赖: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
