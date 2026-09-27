"""
app.py — Gradio UI（LangGraph 版，停止 + 保留输入 + 批量删除）
"""
from __future__ import annotations

import os
import queue
import threading
import time
import uuid
from collections.abc import Generator

import gradio as gr

from .model.agent import (
    cancel_task,
    get_session,
    modify_task,
    resume_task,
    retry_node_cmd,
    run_task_stream,
)
from .config import DEBUG, GRADIO_HOST, GRADIO_PORT, RENDER_DIR
from .model.logger_setup import get_logger, set_req_id

logger = get_logger(__name__)

# ══════════════════════════════════════════════════
#  数据库初始化
# ══════════════════════════════════════════════════
try:
    from .model.database import init_db as _init_db
    _init_db()
except Exception as e:
    logger.warning("[App] 数据库初始化失败: %s", e)


# ══════════════════════════════════════════════════
#  Gradio 全局 JS / CSS
# ══════════════════════════════════════════════════
GLOBAL_HEAD = """
<style>
.node-modal-overlay {
    display:none; position:fixed; top:0; left:0;
    width:100%; height:100%;
    background:rgba(0,0,0,0.4); z-index:9998;
}
.node-modal {
    display:none; position:fixed; top:50%; left:50%;
    transform:translate(-50%,-50%);
    width:min(700px,92vw); max-height:82vh;
    background:white; border-radius:16px;
    box-shadow:0 25px 70px rgba(0,0,0,0.25); z-index:9999;
    overflow:hidden;
}
.node-modal-header {
    padding:22px 28px;
    background:linear-gradient(135deg,#1e40af,#1e3a8a);
    color:white; display:flex;
    justify-content:space-between; align-items:center;
}
.node-modal-body {
    padding:20px 28px 24px; overflow-y:auto;
    max-height:58vh; font-size:14px; line-height:1.9;
}
</style>
<script>
window.__flowchartCards = {};
document.addEventListener('DOMContentLoaded', function() {
    var observer = new MutationObserver(function() {
        document.querySelectorAll('[data-flowchart-data]').forEach(function(el) {
            var cardsStr = el.getAttribute('data-cards');
            if (cardsStr) {
                try { window.__flowchartCards = JSON.parse(cardsStr); } catch(e) {}
                el.removeAttribute('data-flowchart-data');
            }
        });
    });
    observer.observe(document.body, {childList:true, subtree:true});
});
function showNodeModal(nodeId) {
    var card = window.__flowchartCards[nodeId];
    if (!card) return;
    var title = document.getElementById('global-modal-title');
    var body = document.getElementById('global-modal-body');
    if (title) title.textContent = card.name;
    if (body) body.innerHTML = card.details;
    var overlay = document.getElementById('global-node-modal-overlay');
    var modal = document.getElementById('global-node-modal');
    if (overlay) overlay.style.display = 'block';
    if (modal) modal.style.display = 'block';
}
function closeNodeModal() {
    var overlay = document.getElementById('global-node-modal-overlay');
    var modal = document.getElementById('global-node-modal');
    if (overlay) overlay.style.display = 'none';
    if (modal) modal.style.display = 'none';
}
</script>
"""


# ══════════════════════════════════════════════════
#  任务提交
# ══════════════════════════════════════════════════
def create_new_task(
    user_input: str,
    enable_refine: bool,
    thread_id: str | None = None,
) -> Generator[
    tuple[str, gr.HTML, str, gr.HTML, gr.Markdown, str, bool, bool],
    None,
    None,
]:
    rid = set_req_id()
    logger.info("[App] 新任务 | refine=%s req=%s", enable_refine, rid)

    # 校验
    if not user_input or not user_input.strip():
        yield (
            "⚠️ 请输入任务需求", gr.HTML(""), "", gr.HTML(
                ""), gr.Markdown(visible=False),
            thread_id or "", False, False,
        )
        return

    if len(user_input) > 2000:
        yield (
            "⚠️ 输入过长（最多 2000 字符），请精简后重试", gr.HTML(
                ""), "", gr.HTML(""), gr.Markdown(visible=False),
            thread_id or "", False, False,
        )
        return

    # 生成 thread_id
    if not thread_id:
        thread_id = str(uuid.uuid4())

    yield (
        "🚀 任务已提交，正在启动...", gr.HTML(""), thread_id, gr.HTML(
            ""), gr.Markdown(visible=False),
        thread_id, True, False,
    )

    try:
        for snapshot in run_task_stream(user_input.strip(), thread_id, enable_refine):
            elapsed = time.time() - time.time()  # 近似值，session 里有 start_time

            if snapshot.get("type") == "error":
                yield (
                    f"❌ 任务失败", gr.HTML(""), thread_id,
                    gr.HTML(f"<div style='color:#cc0000;'>{
                            snapshot.get('error', '')}</div>"),
                    gr.Markdown(visible=False), thread_id, False, False,
                )
                return

            svg = snapshot.get("svg", "")
            direct = snapshot.get("direct_response", "")
            task_id = snapshot.get("task_id", "")
            status = snapshot.get("status_text", "")
            error = snapshot.get("error", "")

            if direct:
                yield (
                    status or "✅ 已处理", gr.HTML(""), task_id, gr.HTML(""),
                    gr.Markdown(direct, visible=True), thread_id, False, False,
                )
            elif error:
                yield (
                    "❌ 任务失败", gr.HTML(svg, visible=bool(svg)), task_id,
                    gr.HTML(f"<div style='color:#cc0000;'>{error}</div>"),
                    gr.Markdown(visible=False), thread_id, False, False,
                )
            else:
                step_text = snapshot.get("steps", [])
                last_step = step_text[-1] if step_text else "处理中..."
                yield (
                    f"{last_step} ({elapsed:.0f}s)" if elapsed else last_step,
                    gr.HTML(svg, visible=bool(svg)),
                    task_id, gr.HTML(""), gr.Markdown(visible=False),
                    thread_id, True, False,
                )

    except (RuntimeError, TimeoutError) as exc:
        logger.exception("[App] 异常 (req=%s)", rid)
        yield (
            "❌ 系统异常", gr.HTML(""), thread_id or "",
            gr.HTML(f"<div style='color:#cc0000;'>{exc}</div>"),
            gr.Markdown(visible=False), thread_id or "", False, False,
        )


def stop_task(thread_id: str, user_input: str) -> tuple[str, gr.HTML, str, gr.HTML, gr.Markdown, str, bool, bool]:
    """停止任务，保留输入框内容"""
    if thread_id:
        cancel_task(thread_id)
    return (
        "⏹️ 已停止（输入已保留，可修改后重新提交）",
        gr.HTML(""), thread_id, gr.HTML(""), gr.Markdown(visible=False),
        thread_id, False, False,
    )


# ══════════════════════════════════════════════════
#  历史记录
# ══════════════════════════════════════════════════
def _init_history_dropdown():
    try:
        from .model.database import list_tasks
        tasks = list_tasks(limit=50)
        if not tasks:
            return gr.Dropdown(choices=[], value=None)
        choices = [
            (f"{t['title'][:30]} | {t['task_id'][-8:]}", t["task_id"])
            for t in tasks
        ]
        return gr.Dropdown(choices=choices, value=tasks[0]["task_id"])
    except Exception as e:
        logger.warning("[App] 加载历史失败: %s", e)
        return gr.Dropdown(choices=[], value=None)


def load_history_detail(task_id: str) -> tuple[str, str, str, str]:
    """返回 (svg, detail_md, status_text, original_input)"""
    if not task_id:
        return "", "请选择一个任务", "", ""
    try:
        from .model.database import load_task_with_plan
        data = load_task_with_plan(task_id)
        if not data:
            return "", f"任务不存在: {task_id}", "", ""

        task = data["task"]
        plan = data["plan"]

        from .model.flowchart_pro import render_for_gradio
        svg = render_for_gradio(plan.get("nodes", []),
                                plan.get("edges", []), task_id, "")

        status_names = {0: "⏳ 待处理", 1: "🔄 进行中",
                        2: "✅ 成功", 3: "❌ 失败", 4: "⏰ 超时"}
        detail_lines = [
            f"**任务 ID**: `{task_id}`",
            f"**原始输入**: {task.get('raw_query', '')}",
            f"**状态**: {status_names.get(task.get('status', 0), '?')}",
            f"**意图**: {task.get('intent_info', {}).get('summary', '')}",
            f"**节点数**: {len(plan.get('nodes', []))}",
            "",
            "**节点列表**:",
        ]
        for n in plan.get("nodes", []):
            icon = {0: "⏳", 1: "🔄", 2: "✅", 3: "❌"}.get(
                n.get("status", 0), "?")
            detail_lines.append(f"  {icon} #{n['id']} {n['name']}")

        status_text = f"📜 已加载: {task.get('raw_query', '')[:40]}"
        return svg, "\n".join(detail_lines), status_text, task.get("raw_query", "")
    except Exception as e:
        logger.error("[App] 加载历史详情失败: %s", e)
        return "", f"加载失败: {e}", "", ""


def delete_selected_tasks(task_ids: list[str]) -> tuple[gr.Dropdown, str]:
    """删除选中的任务（支持批量）"""
    if not task_ids:
        return gr.Dropdown(), "⚠️ 请先选择要删除的任务"
    try:
        from .model.database import batch_delete_tasks
        count = batch_delete_tasks(task_ids)
        # 刷新 dropdown
        from .model.database import list_tasks
        tasks = list_tasks(limit=50)
        if not tasks:
            return gr.Dropdown(choices=[], value=None), f"✅ 已删除 {count} 个任务"
        choices = [
            (f"{t['title'][:30]} | {t['task_id'][-8:]}", t["task_id"])
            for t in tasks
        ]
        return (
            gr.Dropdown(choices=choices, value=None),
            f"✅ 已删除 {count} 个任务",
        )
    except Exception as e:
        logger.error("[App] 删除失败: %s", e)
        return gr.Dropdown(), f"❌ 删除失败: {e}"


# ══════════════════════════════════════════════════
#  导出功能
# ══════════════════════════════════════════════════
def export_task(task_id: str, fmt: str) -> tuple[str, str | None]:
    if not task_id:
        return "⚠️ 请先选择一个任务", None
    try:
        from .model.database import load_task_with_plan
        from .model.flowchart_pro import render_for_gradio

        data = load_task_with_plan(task_id)
        if not data:
            return f"❌ 任务不存在: {task_id}", None

        plan = data["plan"]
        nodes = plan.get("nodes", [])
        edges = plan.get("edges", [])

        os.makedirs(RENDER_DIR, exist_ok=True)
        ext_map = {"png": ".png", "pdf": ".pdf", "svg": ".svg",
                   "json": ".json", "html": ".html", "dot": ".dot"}
        ext = ext_map.get(fmt, ".txt")
        filename = f"{task_id}_export{ext}"
        filepath = os.path.join(RENDER_DIR, filename)

        if fmt == "svg":
            import re
            svg_content = render_for_gradio(nodes, edges, task_id, "")
            svg_match = re.search(
                r'<svg[^>]*>.*</svg>', svg_content, re.DOTALL)
            svg_text = svg_match.group(0) if svg_match else svg_content
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(svg_text)
        elif fmt in ("png", "pdf"):
            import cairosvg
            import re
            svg_content = render_for_gradio(nodes, edges, task_id, "")
            svg_match = re.search(
                r'<svg[^>]*>.*</svg>', svg_content, re.DOTALL)
            svg_text = svg_match.group(0) if svg_match else svg_content
            if fmt == "png":
                cairosvg.svg2png(bytestring=svg_text.encode(
                    "utf-8"), write_to=filepath, dpi=300)
            else:
                cairosvg.svg2pdf(bytestring=svg_text.encode(
                    "utf-8"), write_to=filepath)
        elif fmt == "json":
            import json
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump({"nodes": nodes, "edges": edges},
                          f, ensure_ascii=False, indent=2)
        elif fmt == "html":
            html = render_for_gradio(nodes, edges, task_id, "")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
        elif fmt == "dot":
            import networkx as nx
            from networkx.drawing.nx_pydot import to_pydot
            G = nx.DiGraph()
            for n in nodes:
                G.add_node(n["id"], label=n.get("name", f"步骤{n['id']}"))
            for e in edges:
                G.add_edge(e["from"], e["to"], label=e.get("label", ""))
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(to_pydot(G).to_string())

        return f"✅ 已导出为 {fmt.upper()} → {filename}", filepath
    except Exception as e:
        logger.error("[App] 导出失败: %s", e)
        return f"❌ 导出失败: {e}", None


# ══════════════════════════════════════════════════
#  vis-network 配置 —— 全部放在 HEAD 里，不用 js_on_load
# ══════════════════════════════════════════════════
VIS_HEAD = '''
<script src="https://cdn.jsdelivr.net/npm/vis-network@9.1.2/dist/vis-network.min.js"></script>
<script>
(function() {
    if (window.__visObserverInited) return;
    window.__visObserverInited = true;
    window.__visExecuted = new Set();
    
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) {
                    var scripts = node.querySelectorAll ? node.querySelectorAll('script') : [];
                    for (var i = 0; i < scripts.length; i++) {
                        var s = scripts[i];
                        if (!window.__visExecuted.has(s)) {
                            window.__visExecuted.add(s);
                            try {
                                var newScript = document.createElement('script');
                                newScript.text = s.text;
                                document.head.appendChild(newScript);
                                // 执行完立即移除，防止被再次捡到
                                setTimeout(function() {
                                    if (newScript.parentNode) {
                                        newScript.parentNode.removeChild(newScript);
                                    }
                                }, 0);
                            } catch(e) {
                                console.error('[vis] script exec error:', e);
                            }
                        }
                    }
                }
            });
        });
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
'''

# ══════════════════════════════════════════════════
#  构建 UI
# ══════════════════════════════════════════════════


def build_app():
    with gr.Blocks(title="通用任务规划助手") as app:
        gr.Markdown("# 🧠 通用任务规划助手")
        gr.Markdown("输入任务需求，AI 自动分解为 DAG 流程图并逐步执行。（最多 2000 字符）")

        thread_id_state = gr.Textbox(visible=False, label="thread_id")

        with gr.Tabs():
            # ── Tab 1: 新建任务 ──
            with gr.Tab("🚀 新建任务"):
                with gr.Row():
                    user_input = gr.Textbox(
                        label="任务需求", placeholder="例如：教我做甜口西红柿炒鸡蛋",
                        lines=3, scale=4, max_lines=10,
                    )
                    enable_refine = gr.Checkbox(
                        label="节点细化", value=True, scale=1)

                with gr.Row():
                    submit_btn = gr.Button("🚀 开始规划", variant="primary")
                    stop_btn = gr.Button(
                        "⏹️ 停止", variant="stop", interactive=False)

                status_output = gr.Textbox(label="状态", interactive=False)
                graph_output = gr.HTML(
                    label="流程图", head=VIS_HEAD)
                task_id_display = gr.Textbox(visible=False, label="task_id")
                error_box = gr.HTML(visible=False)
                ai_reply = gr.Markdown(visible=False)

                # 提交
                submit_btn.click(
                    fn=create_new_task,
                    inputs=[user_input, enable_refine, thread_id_state],
                    outputs=[
                        status_output, graph_output, task_id_display,
                        error_box, ai_reply, thread_id_state,
                        # stop_btn interactive, submit_btn interactive
                        gr.State(value=True), gr.State(value=False),
                    ],
                ).then(
                    lambda: (gr.Button(interactive=True),
                             gr.Button(interactive=False)),
                    outputs=[stop_btn, submit_btn],
                )

                # 停止
                stop_btn.click(
                    fn=stop_task,
                    inputs=[thread_id_state, user_input],
                    outputs=[
                        status_output, graph_output, task_id_display,
                        error_box, ai_reply, thread_id_state,
                        gr.State(value=False), gr.State(
                            value=True),  # stop_btn, submit_btn
                    ],
                ).then(
                    lambda: (gr.Button(interactive=False),
                             gr.Button(interactive=True)),
                    outputs=[stop_btn, submit_btn],
                )

            # ── Tab 2: 历史记录 ──
            with gr.Tab("📜 历史记录"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### 📋 任务列表")
                        refresh_btn = gr.Button("🔄 刷新列表", variant="secondary")
                        history_dropdown = gr.Dropdown(
                            label="选择历史任务（可多选删除）",
                            choices=[], value=None,
                            interactive=True, filterable=True,
                            multiselect=True,
                        )
                        delete_btn = gr.Button("🗑️ 删除选中", variant="stop")
                        delete_status = gr.Textbox(
                            label="删除状态", interactive=False)

                        gr.Markdown("### 📥 导出")
                        with gr.Group():
                            export_format = gr.Radio(
                                label="导出格式",
                                choices=[("PNG", "png"), ("PDF", "pdf"), ("SVG", "svg"),
                                         ("JSON", "json"), ("HTML", "html"), ("DOT", "dot")],
                                value="png",
                            )
                            export_btn = gr.Button(
                                "⬇️ 导出选中任务", variant="primary")
                            export_file = gr.File(
                                label="下载文件", interactive=False)
                            export_status = gr.Textbox(
                                label="导出状态", interactive=False)

                    with gr.Column(scale=2):
                        gr.Markdown("### 🗺️ 流程图")
                        history_svg = gr.HTML(
                            label="流程图预览", elem_id="history-flowchart", head=VIS_HEAD)
                        gr.Markdown("### 📝 任务详情")
                        history_detail = gr.Markdown(label="详情")

                # 加载历史
                app.load(fn=_init_history_dropdown, outputs=[history_dropdown])

                def _on_refresh():
                    dd = _init_history_dropdown()
                    tid = dd.value[0] if dd.value else None
                    svg, detail, status, orig_input = load_history_detail(
                        tid or "")
                    return dd, svg, detail, status, orig_input

                refresh_btn.click(
                    fn=_on_refresh,
                    outputs=[history_dropdown, history_svg,
                             history_detail, export_status, user_input],
                )

                history_dropdown.change(
                    fn=lambda tids: load_history_detail(
                        tids[0] if tids else ""),
                    inputs=[history_dropdown],
                    outputs=[history_svg, history_detail,
                             export_status, user_input],
                )

                # 删除
                delete_btn.click(
                    fn=delete_selected_tasks,
                    inputs=[history_dropdown],
                    outputs=[history_dropdown, delete_status],
                )

                # 导出
                export_btn.click(
                    fn=export_task,
                    inputs=[history_dropdown, export_format],
                    outputs=[export_status, export_file],
                )

    return app


def main():
    app = build_app()
    logger.info("🚀 启动 | %s:%s debug=%s", GRADIO_HOST, GRADIO_PORT, DEBUG)
    app.launch(
        server_name=GRADIO_HOST,
        server_port=GRADIO_PORT,
        debug=DEBUG,
        head=GLOBAL_HEAD,
    )


if __name__ == "__main__":
    main()
