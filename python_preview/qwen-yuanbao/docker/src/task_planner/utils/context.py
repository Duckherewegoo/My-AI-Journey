from contextlib import contextmanager
import contextvars
import threading

cancel_event_var: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "cancel_event", default=None
)


@contextmanager
def cancel_scope(event: threading.Event):
    """安全地设置取消信号的上下文管理器"""
    token = cancel_event_var.set(event)
    try:
        yield event
    finally:
        cancel_event_var.reset(token)
