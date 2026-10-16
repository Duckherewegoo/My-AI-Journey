from task_planner.infrastructure.config import HISTORY_LABEL_MAX_LEN


def build_history_dropdown_options(tasks: list[dict]) -> list[dict]:
    """统一构建历史任务下拉选项，避免多处重复"""
    options = []
    for t in tasks:
        title = str(t.get("title", ""))[:HISTORY_LABEL_MAX_LEN]
        tid_suffix = str(t.get("task_id", ""))[-8:]
        options.append({
            "label": f"{title} | {tid_suffix}",
            "value": t["task_id"],
        })
    return options


def extract_first_task_id(task_ids) -> str | None:
    """安全提取第一个任务ID，兼容 list/单值/None"""
    if not task_ids:
        return None
    if isinstance(task_ids, list):
        return task_ids[0] if task_ids else None
    return task_ids
