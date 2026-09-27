"""
logger_setup.py — 日志系统（生产最终版）
════════════════════════════════════════════════
  ✅ ContextVar 自动注入 req_id（Gradio 子线程安全）
  ✅ 控制台 + 文件双输出
  ✅ 文件按天轮转，保留 7 天
  ✅ DEBUG 模式控制台开 INFO+，否则 WARNING+
  ✅ 模块级 get_logger / set_req_id / get_req_id 三件套
"""

import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar
import threading
from task_planner.infrastructure.config import DEBUG, LOG_CONSOLE_LEVEL, LOG_DIR, LOG_FILE, LOG_MAX_DAYS

# ═══════════════════════════════════════════════
#  ContextVar：自动传递 req_id 到所有日志
# ═══════════════════════════════════════════════
req_id_var: ContextVar[str] = ContextVar("req_id", default="-")


class ReqIdFilter(logging.Filter):
    """自动给每条日志加上 req_id 属性"""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = req_id_var.get()
        if not hasattr(record, "req_id"):
            record.req_id = rid if rid != "-" else "-"
        return True


# ═══════════════════════════════════════════════
#  ReqIdLogger：makeRecord 阶段强制注入 req_id
# ═══════════════════════════════════════════════
class ReqIdLogger(logging.Logger):
    """自定义 Logger：在 makeRecord 阶段强制注入 req_id"""

    def makeRecord(
        self,
        name: str,
        level: int,
        fn: str,
        lno: int,
        msg: str,
        args: tuple,
        exc_info,
        func: str | None = None,
        extra: dict | None = None,
        sinfo: str | None = None,
    ) -> logging.LogRecord:
        extra = dict(extra) if extra else {}
        extra.setdefault("req_id", req_id_var.get())
        return super().makeRecord(
            name,
            level,
            fn,
            lno,
            msg,
            args,
            exc_info,
            func=func,
            extra=extra,
            sinfo=sinfo,
        )


# 注册自定义 Logger 类（必须在任何 logger 创建前）
logging.setLoggerClass(ReqIdLogger)


# ═══════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════
def make_req_id() -> str:
    """生成 8 字符短格式请求 ID"""
    return uuid.uuid4().hex[:8]


def set_req_id(rid: str | None = None) -> str:
    """设置当前上下文的 req_id，返回设置的值"""
    rid = rid or make_req_id()
    req_id_var.set(rid)
    return rid


def get_req_id() -> str:
    """获取当前线程/协程的 req_id"""
    return req_id_var.get()


# ═══════════════════════════════════════════════
#  初始化
# ═══════════════════════════════════════════════
_init_lock = threading.Lock()


def setup_logger(name: str = "task_planner") -> ReqIdLogger:
    """初始化 logger（幂等，重复调用直接返回）"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # type: ignore
    with _init_lock:
        if logger.handlers:  # Double-check locking
            return logger  # type: ignore

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, LOG_FILE)

    fmt = (
        "%(asctime)s | %(levelname)-7s | %(name)s [%(filename)s:%(lineno)d] "
        "| [req=%(req_id)s] %(message)s"
    )
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt=datefmt)

    # 控制台
    console_level = getattr(
        logging, LOG_CONSOLE_LEVEL.upper(), logging.WARNING)
    ch = logging.StreamHandler()
    ch.setLevel(console_level)
    ch.setFormatter(formatter)
    ch.addFilter(ReqIdFilter())

    # 文件（按天轮转 7 天，始终 DEBUG）
    fh = logging.handlers.TimedRotatingFileHandler(
        filename=log_path,
        when="midnight",
        interval=1,
        backupCount=LOG_MAX_DAYS,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    fh.addFilter(ReqIdFilter())

    logger.setLevel(logging.DEBUG)
    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.propagate = False

    logger.info(
        "🔧 日志系统初始化完成 (debug=%s, console=%s, file=DEBUG, retain=%d天)",
        DEBUG,
        LOG_CONSOLE_LEVEL,
        LOG_MAX_DAYS,
    )
    return logger  # type: ignore


# 别名（兼容各模块引用方式）
get_logger = setup_logger
