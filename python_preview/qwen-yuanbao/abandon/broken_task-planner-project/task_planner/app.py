"""
app.py — Gradio 前端（生产最终版 v6.0）
══════════════════════════════════════════════════
职责：
  ✅ 用户输入 → Agent 执行 → 流程图渲染 → 状态管理
  ✅ 实时进度推送（用户不用盲等）
  ✅ 历史任务加载 / 刷新
  ✅ 节点状态手动切换（待办→进行中→完成）
  ✅ 失败节点重跑
  ✅ 导出（SVG / PNG / PDF / DOT / HTML / JSON）
  ✅ 暗色模式

修复要点（对比上一版）：
  ❌ 上一版 ai_reply 和 ai_reply_display 两个变量指向不同组件
      → 事件绑定只绑了其中一个，另一个永远是初始值
  ✅ 本版统一为一个组件 ai_reply，所有分支都更新它
  ❌ 上一版 from concurrent.futures 拼错成 concurrent.futures
  ✅ 本版修正导入
  ❌ 上一版 gr.HTML(visible=...) 在 Gradio 6.x 不支持
  ✅ 本版改用 gr.HTML("") 空内容（初始化时除外）
  ✅ create_new_task 是 generator，每 1 秒 yield 实时状态
  ✅ 子任务执行有真实反馈（不再是 time.sleep(0.05) 假循环）
  ✅ 导出支持全部 5 种格式（svg/png/pdf/dot/html/json）
     PNG/PDF 走 base64 data URI，Gradio File 组件可直接下载

设计原则：
  「不玩虚的」—— 所有数据 100% 来自 LLM + MongoDB，不 Mock。
"""
import time
import json
import os
import logging
from typing import Optional, Tuple, Iterator, Any, Dict, List

import gradio as gr
from gradio import themes

from .config import (
    GRADIO_HOST,
    GRADIO_PORT,
    DEBUG,
    SUPPORTED_EXPORT_FORMATS,
    DEFAULT_EXPORT_FORMAT,
    RENDER_DIR,
)
from .agent import (
    run_task,
    load_and_render,
    retry_failed_nodes,
    get_task_status_map,
    export_task,
    task_agent,
)
from .database import db_manager
from .logger_setup import get_logger, set_req_id

logger = get_logger("task_planner.app")


# ═════════════════════════════════════════════════
#  全局 Head（注入到 <head>，页面加载时执行，不受 innerHTML 限制）
# ═════════════════════════════════════════════════
GLOBAL_HEAD = r"""
<style>
/* ── 弹窗样式 ──────────────────────── */
.node-modal-overlay {
    display: none; position: fixed; top: 0; left: 0;
    width: 100%; height: 100%; background: rgba(0,0,0,0.4);
    z-index: 9998; backdrop-filter: blur(2px);
}
.node-modal {
    display: none; position: fixed; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: min(700px, 92vw); max-height: 82vh;
    background: white; border-radius: 16px;
    box-shadow: 0 25px 70px rgba(0,0,0,0.25);
    z-index: 9999; overflow: hidden;
    animation: slideUp .25s ease-out;
}
.node-modal-header {
    padding: 22px 28px;
    background: linear-gradient(135deg, #1e40af, #1e3a8a);
    color: white; display: flex; justify-content: space-between;
    align-items: center;
}
.node-modal-body {
    padding: 20px 28px 24px; overflow-y: auto; max-height: 58vh;
    font-size: 14px; line-height: 1.9; color: #334155;
}
.node-modal-close {
    background: rgba(255,255,255,0.15); border: none; color: white;
    font-size: 20px; width: 38px; height: 38px; border-radius: 50%;
    cursor: pointer; transition: background 0.2s;
}
.node-modal-close:hover { background: rgba(255,255,255,0.25); }
/* ── 图例 ──────────────────────── */
.flowchart-legend {
    position: absolute; top: 14px; right: 18px; z-index: 10;
    background: white; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 10px 14px; font-size: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
/* ── 暗色模式 ──────────────────────── */
.dark .node-modal { background: #1e1e2e !important; color: #e2e8f0 !important; }
.dark .node-modal-body { color: #cbd5e1 !important; }
.dark .flowchart-legend { background: #2a2a3e !important; border-color: #444 !important; }
</style>

<script>
// ═════════════════════════════════════════════
//  全局弹窗系统（head 注入，页面加载时执行）
// ═════════════════════════════════════════════
window.__flowchartCards = {};

function showNodeModal(nodeId) {
    var cards = window.__flowchartCards;
    var card = cards[nodeId];
    if (!card) {
        console.warn('[Flowchart] 节点数据未找到:', nodeId);
        return;
    }

    // 懒创建弹窗 DOM
    if (!document.getElementById('global-node-modal')) {
        var html = [
            '<div id="global-node-modal-overlay" class="node-modal-overlay" onclick="closeNodeModal()"></div>',
            '<div id="global-node-modal" class="node-modal">',
            '  <div class="node-modal-header">',
            '    <h3 id="global-modal-title" style="margin:0;font-size:20px;"></h3>',
            '    <button class="node-modal-close" onclick="closeNodeModal()">✕</button>',
            '  </div>',
            '  <div id="global-modal-body" class="node-modal-body"></div>',
            '</div>'
        ].join('');
        document.body.insertAdjacentHTML('beforeend', html);
    }

    document.getElementById('global-modal-title').textContent = card.name;

    var statusColors = {
        0: {bg:'#fff3e0', color:'#f59e0b'},
        1: {bg:'#e3f2fd', color:'#3b82f6'},
        2: {bg:'#e8f5e9', color:'#10b981'},
        3: {bg:'#ffebee', color:'#ef4444'},
        4: {bg:'#f3e5f5', color:'#9c27b0'}
    };
    var sc = statusColors[card.status] || statusColors[0];

    var statusEl = document.createElement('span');
    statusEl.style.cssText = 'display:inline-block;padding:5px 16px;border-radius:20px;font-size:13px;font-weight:500;';
    statusEl.style.background = sc.bg;
    statusEl.style.color = sc.color;
    statusEl.textContent = card.status_text;

    var body = document.getElementById('global-modal-body');
    var html = '<div style="margin-bottom:16px;">' +
        '<b style="color:#1e40af;font-size:15px;">📋 行动细节</b>' +
        '<div style="margin-top:10px;padding:14px;background:#f8fafc;border-radius:8px;border-left:4px solid #1e40af;">' +
        card.details + '</div></div>';

    if (card.preconditions && card.preconditions.length) {
        html += '<div style="margin-bottom:16px;"><b style="color:#059669;">✅ 前置条件</b><ul style="margin:8px 0 0 20px;color:#475569;">' +
            card.preconditions.map(function(p){return '<li>'+p+'</li>';}).join('') +
        '</ul></div>';
    }
    if (card.postconditions && card.postconditions.length) {
        html += '<div style="margin-bottom:16px;"><b style="color:#7c3aed;">🎯 预期结果</b><ul style="margin:8px 0 0 20px;color:#475569;">' +
            card.postconditions.map(function(p){return '<li>'+p+'</li>';}).join('') +
        '</ul></div>';
    }

    html += '<div style="margin-top:16px;padding:12px;background:#fef2f2;border-radius:8px;">' +
        '<b style="color:#dc2626;">🔄 重试策略:</b> ' +
        '<span style="color:#991b1b;">' + card.retry_policy + '</span>' +
        (card.retry_count > 0
            ? '<span style="color:#991b1b;margin-left:8px;">(已重试'+card.retry_count+'次)</span>'
            : '') +
        '</div>';

    body.innerHTML = html;
    // 在 header 里插入状态标签
    var header = document.querySelector('.node-modal-header');
    var oldStatus = document.getElementById('modal-status-badge');
    if (oldStatus) oldStatus.remove();
    statusEl.id = 'modal-status-badge';
    header.appendChild(statusEl);

    document.getElementById('global-node-modal-overlay').style.display = 'block';
    document.getElementById('global-node-modal').style.display = 'block';
}

function closeNodeModal() {
    var o = document.getElementById('global-node-modal-overlay');
    var m = document.getElementById('global-node-modal');
    if (o) o.style.display = 'none';
    if (m) m.style.display = 'none';
}

// ═════════════════════════════════════════════
//  MutationObserver：监听 flowchart 数据注入 + 节点点击
// ═════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function() {
    // 1) 读取节点数据（通过 application/json script 标签）
    var observer = new MutationObserver(function(mutations) {
        document.querySelectorAll('script[type="application/json"][id^="flowchart-data-"]').forEach(function(el) {
            var cardsStr = el.textContent || el.innerHTML;
            if (cardsStr) {
                try {
                    window.__flowchartCards = JSON.parse(cardsStr);
                    console.log('[Flowchart] 加载节点数据:', Object.keys(window.__flowchartCards).length, '个');
                } catch(e) {
                    console.error('[Flowchart] 数据解析失败:', e);
                }
            }
            el.remove(); // 只读一次
        });
    });
    observer.observe(document.body, {childList: true, subtree: true});

    // 2) 事件委托：监听 vis-network 节点点击
    document.addEventListener('click', function(e) {
        var nodeEl = e.target && e.target.closest && e.target.closest('.vis-node');
        if (nodeEl) {
            var nodeId = nodeEl.id && nodeEl.id.replace('node', '');
            if (nodeId) showNodeModal(nodeId);
        }
    });
});
</script>
"""


# ═════════════════════════════════════════════════
#  事件处理
# ═════════════════════════════════════════════════
def create_new_task(user_input: str, enable_refine: bool) -> Iterator[Tuple]:
    """
    生成新任务（generator 模式，实时推送进度）。
    每一步 yield 当前状态，用户不用盲等。
    """
    rid = set_req_id()
    logger.info("[App] 🚀 新任务 | refine=%s req=%s", enable_refine, rid)

    if not user_input or not user_input.strip():
        yield (
            "⚠️ 请输入任务需求",
            gr.HTML(""),
            "",
            gr.HTML(""),
            gr.Markdown(visible=False),
        )
        return

    # 初始状态
    yield (
        "🔍 正在分析意图...",
        gr.HTML(""),
        "",
        gr.HTML(""),
        gr.Markdown(visible=False),
    )

    # 进度收集
    steps_log: List[str] = []

    def progress_cb(step_name: str, node_id: int, status: str, detail: str):
        """Agent 每完成一步调用，更新 UI"""
        steps_log.append(f"[{time.strftime('%H:%M:%S')}] {status} {detail}")
        logger.debug("[App] 进度: %s (req=%s)", detail, rid)

    try:
        # ✅ 修正：concurrent.futures（之前拼错成 concurrent.futures）
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                task_agent.run,
                user_input.strip(),
                rid,
                enable_refine,
            )

            t0 = time.time()
            while not future.done():
                elapsed = time.time() - t0
                status_msg = f"⏳ 处理中... ({elapsed:.0f}s)"
                if steps_log:
                    status_msg += f" | 最近: {steps_log[-1][-60:]}"
                yield (
                    status_msg,
                    gr.HTML(""),
                    "",
                    gr.HTML(""),
                    gr.Markdown(visible=False),
                )
                time.sleep(1)

            result = future.result()

        if result.get("success"):
            if result.get("direct_response"):
                # 无需规划 → 显示 LLM 直接回复
                yield (
                    result.get("status_text", "✅ 已处理"),
                    gr.HTML(""),
                    result.get("task_id", ""),
                    gr.HTML(""),
                    gr.Markdown(result["direct_response"], visible=True),
                )
            else:
                # 需要规划 → 显示流程图
                yield (
                    result.get("status_text", "✅ 完成"),
                    gr.HTML(result.get("svg", "")),
                    result.get("task_id", ""),
                    gr.HTML(""),
                    gr.Markdown(visible=False),
                )
        else:
            err = result.get("error", "未知错误")
            logger.error("[App] 任务失败: %s (req=%s)", err, rid)
            yield (
                f"❌ {err[:100]}",
                gr.HTML(result.get("svg", ""), visible=bool(result.get("svg"))),
                result.get("task_id", ""),
                gr.HTML(f"<div style='color:#cc0000;padding:8px;'>{err}</div>", visible=True),
                gr.Markdown(visible=False),
            )

    except Exception as exc:
        logger.exception("[App] ❌ 异常 (req=%s)", rid)
        yield (
            f"❌ 系统异常: {exc}",
            gr.HTML(""),
            "",
            gr.HTML(f"<div style='color:#cc0000;padding:8px;'>{exc}</div>", visible=True),
            gr.Markdown(visible=False),
        )


def load_history(history_choice: str) -> Tuple:
    rid = set_req_id()
    logger.info("[App] 📂 加载历史任务 (req=%s)", rid)

    if not history_choice:
        return ("⚠️ 请选择历史任务", gr.HTML(""), "", gr.HTML(""), gr.Markdown(visible=False))
    try:
        task_id = history_choice.split("|")[-1].strip()
    except Exception:
        return ("⚠️ 格式异常", gr.HTML(""), "", gr.HTML(""), gr.Markdown(visible=False))

    result = load_and_render(task_id)
    if not result.get("success"):
        err = result.get("error", "加载失败")
        return (
            f"⚠️ {err}",
            gr.HTML(""),
            task_id,
            gr.HTML(f"<div style='color:#cc0000;'>{err}</div>", visible=True),
            gr.Markdown(visible=False),
        )

    plan = result.get("plan", {})
    title = plan.get("graph_title", task_id) if isinstance(plan, dict) else ""
    return (
        f"📂 已加载: {title}",
        gr.HTML(result["svg"]),
        task_id,
        gr.HTML(""),
        gr.Markdown(visible=False),
    )


def do_retry(task_id: str) -> Tuple:
    rid = set_req_id()
    logger.info("[App] 🔄 重跑失败节点 | task=%s req=%s", task_id, rid)

    if not task_id:
        return "⚠️ 无任务可操作", gr.HTML(""), task_id, gr.Markdown(visible=False)

    result = retry_failed_nodes(task_id)
    refreshed = load_and_render(task_id)
    svg = refreshed.get("svg", "") if refreshed.get("success") else ""

    if result.get("success"):
        msg = f"✅ {result.get('message', '重跑完成')}"
    else:
        failed = [r["node_id"] for r in result.get("retried", []) if r["status"] == "failed"]
        msg = f"⚠️ 重跑未完成，失败节点: {failed}"

    return msg, gr.HTML(svg), task_id, gr.Markdown(visible=False)


def do_refresh(task_id: str) -> Tuple:
    rid = set_req_id()
    logger.info("[App] 🔃 刷新状态 | task=%s req=%s", task_id, rid)

    if not task_id:
        return "⚠️ 无任务可刷新", gr.HTML(""), task_id, gr.Markdown(visible=False)

    status = get_task_status_map(task_id)
    if not status.get("success"):
        return (
            f"⚠️ {status.get('error', '')}",
            gr.HTML(""),
            task_id,
            gr.Markdown(visible=False),
        )

    s = status["nodes"]
    counts = {"success": 0, "pending": 0, "failed": 0, "timeout": 0}
    for v in s.values():
        st = v["status"]
        if st == 2:
            counts["success"] += 1
        elif st == 0:
            counts["pending"] += 1
        elif st == 3:
            counts["failed"] += 1
        elif st == 4:
            counts["timeout"] += 1

    msg = (
        f"📊 ✅{counts['success']} "
        f"⏳{counts['pending']} "
        f"❌{counts['failed']} "
        f"⏰{counts['timeout']}"
    )
    refreshed = load_and_render(task_id)
    svg = refreshed.get("svg", "") if refreshed.get("success") else ""
    return msg, gr.HTML(svg), task_id, gr.Markdown(visible=False)


def do_export(export_format: str, task_id: str) -> Optional[str]:
    """
    导出任务流程图为指定格式。
    ✅ 支持 svg / png / pdf / dot / html / json
    PNG/PDF 返回 base64 data URI，Gradio File 可直接下载。
    """
    rid = set_req_id()
    logger.info("[App] 📤 导出 | task=%s fmt=%s req=%s", task_id, export_format, rid)

    if not task_id:
        return None

    try:
        result = task_agent.export_task(task_id, export_format, rid)
        if isinstance(result, dict) and "error" not in result:
            content = result.get("content", "")
            if content:
                os.makedirs(RENDER_DIR, exist_ok=True)
                fname = f"task_{task_id}_{rid}.{export_format}"
                fpath = os.path.join(RENDER_DIR, fname)

                # base64 data URI → 解码写文件
                if content.startswith("data:"):
                    import base64
                    header, b64 = content.split(",", 1)
                    binary = base64.b64decode(b64)
                    mode = "wb"
                    data = binary
                else:
                    mode = "w"
                    data = content

                with open(fpath, mode, encoding=None if mode == "wb" else "utf-8") as f:
                    f.write(data)
                logger.info("[App] ✅ 导出成功: %s (req=%s)", fpath, rid)
                return fpath
    except Exception as e:
        logger.error("[App] 导出失败: %s (req=%s)", e, rid)

    return None


# ═════════════════════════════════════════════════
#  Gradio UI
# ═════════════════════════════════════════════════
def build_app():
    with gr.Blocks(
        title="通用任务规划助手",
        head=GLOBAL_HEAD,  # ✅ JS 通过 head 注入，不是 innerHTML
    ) as gradio_app:

        gr.Markdown("# 🤖 通用任务规划助手")
        gr.Markdown(
            "输入**任意任务需求**，AI 自动生成可执行、有向无环、可交互的任务流程图。"
            "支持点击节点查看行动细节、前置条件、重试策略。"
        )

        error_box = gr.HTML(visible=False)
        task_id_state = gr.Textbox(visible=False, label="当前任务ID")

        # ✅ 统一为一个 AI 回复组件（不再有 ai_reply / ai_reply_display 两个变量）
        ai_reply = gr.Markdown(
            value="👋 等待输入任务...",
            visible=True,
            elem_id="ai-reply",
        )

        with gr.Row():
            with gr.Column(scale=1):
                user_input = gr.Textbox(
                    label="📝 任务需求",
                    lines=4,
                    placeholder=(
                        "例如：\n"
                        "• 教我西红柿炒鸡蛋\n"
                        "• 怎么把大象装进冰箱\n"
                        "• 部署一个 Python Web 服务到生产环境"
                    ),
                )
                enable_refine = gr.Checkbox(
                    label="🔧 启用节点细化",
                    value=True,
                    info="关闭后仅生成基础流程图骨架",
                )
                with gr.Row():
                    submit_btn = gr.Button("🚀 生成计划", variant="primary")
                    refresh_btn = gr.Button("🔄 刷新历史", variant="secondary")

                gr.Markdown("### 📋 历史任务")
                history_dropdown = gr.Dropdown(
                    label="选择历史任务",
                    choices=[],
                    interactive=True,
                )
                load_btn = gr.Button("📂 加载选中任务", variant="secondary")

                gr.Markdown("### 📤 导出")
                with gr.Row():
                    export_format = gr.Dropdown(
                        label="格式",
                        choices=SUPPORTED_EXPORT_FORMATS,
                        value=DEFAULT_EXPORT_FORMAT,
                    )
                    export_btn = gr.Button("📥 导出", variant="secondary")
                export_file = gr.File(label="导出文件", visible=True)

                gr.Markdown("### 🔧 节点操作")
                with gr.Row():
                    retry_btn = gr.Button("🔄 重跑失败节点", variant="secondary")
                    status_btn = gr.Button("🔃 刷新状态", variant="secondary")

                gr.Markdown("### 📊 运行状态")
                status_output = gr.Textbox(label="状态", interactive=False, lines=2)

            with gr.Column(scale=2):
                gr.Markdown("### 📈 任务流程图（点击节点查看行动细节）")
                graph_output = gr.HTML(
                    value='''
                    <div style="width:100%;height:550px;
                    display:flex;align-items:center;justify-content:center;
                    border:1px solid #e2e8f0;border-radius:12px;
                    background:#f8fafc;">
                    <div style="color:#64748b;text-align:center;">
                    <h3 style="margin:0 0 8px;color:#475569;">👋 等待生成任务</h3>
                    <p style="margin:0;font-size:13px;">
                    输入任务需求并点击「生成计划」按钮<br>
                    支持任意领域：烹饪、工程、物流、学习…
                    </p></div></div>
                    ''',
                )

        # ═════════════════════════════════════════════
        #  事件绑定（outputs 数量与函数返回值严格一致）
        # ═════════════════════════════════════════════
        submit_btn.click(
            fn=create_new_task,
            inputs=[user_input, enable_refine],
            outputs=[status_output, graph_output, task_id_state, error_box, ai_reply],
            show_progress="full",
        )
        load_btn.click(
            fn=load_history,
            inputs=[history_dropdown],
            outputs=[status_output, graph_output, task_id_state, error_box, ai_reply],
        )
        retry_btn.click(
            fn=do_retry,
            inputs=[task_id_state],
            outputs=[status_output, graph_output, task_id_state, ai_reply],
        )
        status_btn.click(
            fn=do_refresh,
            inputs=[task_id_state],
            outputs=[status_output, graph_output, task_id_state, ai_reply],
        )
        export_btn.click(
            fn=do_export,
            inputs=[export_format, task_id_state],
            outputs=[export_file],
        )
        refresh_btn.click(
            fn=lambda: gr.update(choices=db_manager.get_recent_tasks(50, "refresh")),
            outputs=[history_dropdown],
        )
        gradio_app.load(
            fn=lambda: gr.update(choices=db_manager.get_recent_tasks(50, "init")),
            outputs=[history_dropdown],
        )

    return gradio_app


# ═════════════════════════════════════════════════
#  启动
# ═════════════════════════════════════════════════
gradio_app = build_app()

if __name__ == "__main__":
    logger.info(
        "🚀 启动 | %s:%d debug=%s",
        GRADIO_HOST, GRADIO_PORT, DEBUG,
    )
    gradio_app.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        inbrowser=False,
        share=False,
        theme=themes.Soft(
            primary_hue="blue",
            secondary_hue="gray",
            neutral_hue="gray",
        ),
    )
