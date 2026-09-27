# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  good_addons.py v5.0 — Enterprise Runtime Enhancement Layer        ║
# ║  Pyright strict | PEP-8 compliant | Python 3.9+                    ║
# ║  License: MIT                                                       ║
# ╚══════════════════════════════════════════════════════════════════════╝
"""
good_addons v5.0 — 企业级 Python 运行时增强层。

v5.0 Changes (vs v4.0):
  - CSP 策略：Dash 自动检测并应用兼容策略，不再硬编码 default-src 'self'
  - 请求日志：所有请求均输出（含 method/path/status/耗时），慢请求额外标红
  - 错误处理：后端始终输出完整 traceback，前端返回诊断 JSON
  - Web enhancement 失败时输出详细诊断而非静默 warning
  - Dash 回调级异常捕获：后端记录完整栈 + 审计，前端返回结构化错误
  - 新增 diag() 快速诊断函数，一键输出性能/审计/系统状态

Usage:
    from good_addons import boost
    boost()           # Pure backend enhancement
    boost(app)        # Web framework enhancement (auto-detects Dash/Flask)
"""

from __future__ import annotations

import asyncio
import contextvars
import enum
import functools
import hashlib
import html
import inspect
import json
import logging
import os
import re
import secrets
import signal
import statistics
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Optional Dependencies (Graceful Degradation)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_HAS_PSUTIL = False
_HAS_RICH = False
_HAS_ORJSON = False
_HAS_PYDANTIC = False
_HAS_PROMETHEUS = False
_HAS_CRYPTO = False

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.table import Table
    from rich import box
    _HAS_RICH = True
except ImportError:
    Console = None  # type: ignore
    RichHandler = None  # type: ignore
    Table = None  # type: ignore
    box = None  # type: ignore

try:
    import orjson
    _HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore

try:
    import pydantic
    _HAS_PYDANTIC = True
except ImportError:
    pydantic = None  # type: ignore

try:
    import prometheus_client
    _HAS_PROMETHEUS = True
except ImportError:
    prometheus_client = None  # type: ignore

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except ImportError:
    Fernet = None  # type: ignore

__version__ = "5.0.0"
__all__ = [
    "boost", "trace", "retry", "circuit_breaker", "rate_limited",
    "cached", "validated", "guarded", "debounce", "memoize",
    "EventBus", "RequestContext", "CircuitBreaker", "CircuitOpenError",
    "RateLimitError", "PerformanceMonitor", "SystemMonitor", "Security",
    "MetricsCollector", "AuditLog", "GracefulShutdown",
    "ExceptionFingerprinter", "log", "get_logger",
    "fast_json_dumps", "fast_json_loads", "diag",
]

F = TypeVar("F", bound=Callable[..., Any])
T = TypeVar("T")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Global Context Variables
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_ctx_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_ctx_request_start: contextvars.ContextVar[float] = contextvars.ContextVar("request_start", default=0.0)
_ctx_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


# ╔══════════════════════════════════════════════════╗
# ║  Part 1: Core Infrastructure                    ║
# ╚══════════════════════════════════════════════════╝

class _SingletonMeta(type):
    """Thread-safe Singleton Metaclass."""
    _instances: Dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class EventBus(metaclass=_SingletonMeta):
    """Thread-safe Pub/Sub Event Bus."""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Tuple[int, Callable[..., Any]]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._history: deque[Dict[str, Any]] = deque(maxlen=1000)
        self._seq = 0

    def on(self, event: str, handler: Callable[..., Any], *, priority: int = 0) -> Callable[[], None]:
        with self._lock:
            self._subs[event].append((priority, handler))
            self._subs[event].sort(key=lambda x: -x[0])
        return lambda: self.off(event, handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        with self._lock:
            self._subs[event] = [(p, h) for p, h in self._subs[event] if h is not handler]

    def emit(self, event: str, **kwargs: Any) -> List[Any]:
        with self._lock:
            handlers = list(self._subs.get(event, []))
        self._seq += 1
        self._history.append({"event": event, "kwargs": kwargs, "time": time.time(), "seq": self._seq})
        results = []
        for _, handler in handlers:
            try:
                results.append(handler(**kwargs))
            except Exception as e:
                print(f"[EventBus] Error in {handler.__name__} for {event}: {e}", file=sys.stderr)
        return results

    async def emit_async(self, event: str, **kwargs: Any) -> List[Any]:
        with self._lock:
            handlers = list(self._subs.get(event, []))
        self._seq += 1
        self._history.append({"event": event, "kwargs": kwargs, "time": time.time(), "seq": self._seq})
        results = []
        for _, handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    results.append(await handler(**kwargs))
                else:
                    results.append(handler(**kwargs))
            except Exception as e:
                print(f"[EventBus] Async error in {handler.__name__} for {event}: {e}", file=sys.stderr)
        return results


class RequestContext:
    """Request-scoped context management (async/thread safe)."""

    @staticmethod
    @contextmanager
    def scope(trace_id: str = "", user_id: str = "", **extra: Any) -> Generator[Dict[str, Any], None, None]:
        tid = trace_id or secrets.token_hex(8)
        t1 = _ctx_trace_id.set(tid)
        t2 = _ctx_request_start.set(time.perf_counter())
        t3 = _ctx_user_id.set(user_id)
        ctx = {"trace_id": tid, "user_id": user_id, **extra}
        try:
            yield ctx
        finally:
            _ctx_trace_id.reset(t1)
            _ctx_request_start.reset(t2)
            _ctx_user_id.reset(t3)

    @staticmethod
    def trace_id() -> str: return _ctx_trace_id.get()

    @staticmethod
    def user_id() -> str: return _ctx_user_id.get()

    @staticmethod
    def elapsed() -> float:
        start = _ctx_request_start.get()
        return time.perf_counter() - start if start else 0.0

    @staticmethod
    def snapshot() -> Dict[str, Any]:
        return {
            "trace_id": RequestContext.trace_id(),
            "user_id": RequestContext.user_id(),
            "elapsed_ms": round(RequestContext.elapsed() * 1000, 2),
        }


class PerformanceMonitor(metaclass=_SingletonMeta):
    """Global performance metrics collector."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}

    def record(self, name: str, duration_ms: float, *, error: bool = False) -> None:
        with self._lock:
            if name not in self._stats:
                self._stats[name] = {"count": 0, "errors": 0, "total_ms": 0.0, "times": deque(maxlen=5000)}
            s = self._stats[name]
            s["count"] += 1
            s["total_ms"] += duration_ms
            s["times"].append(duration_ms)
            if error:
                s["errors"] += 1

    def snapshot(self, *, top_n: int = 0, sort_by: str = "total_ms") -> List[Dict[str, Any]]:
        with self._lock:
            items = []
            for name, s in self._stats.items():
                times = list(s["times"])
                if len(times) < 2:
                    continue
                try:
                    q = statistics.quantiles(times, n=100)
                    p50, p95, p99 = q[49], q[94], q[98]
                except Exception:
                    p50 = p95 = p99 = times[0]
                items.append({
                    "name": name, "calls": s["count"], "errors": s["errors"],
                    "total_ms": round(s["total_ms"], 2),
                    "avg_ms": round(s["total_ms"] / s["count"], 2),
                    "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "p99_ms": round(p99, 2),
                    "max_ms": round(max(times), 2),
                })
            items.sort(key=lambda x: x.get(sort_by, 0), reverse=True)
            return items[:top_n] if top_n else items

    def format_table(self, *, top_n: int = 20) -> str:
        items = self.snapshot(top_n=top_n)
        if not items:
            return "(no data)"
        header = f"{'Function':<40} {'Calls':>7} {'Avg':>8} {'P50':>8} {'P95':>8} {'P99':>8} {'Err':>5}"
        sep = "─" * len(header)
        rows = [sep, header, sep]
        for i in items:
            rows.append(
                f"{i['name'][:40]:<40} {i['calls']:>7} {i['avg_ms']:>7.1f}ms "
                f"{i['p50_ms']:>7.1f}ms {i['p95_ms']:>7.1f}ms {i['p99_ms']:>7.1f}ms {i['errors']:>5}"
            )
        rows.append(sep)
        return "\n".join(rows)


# ╔══════════════════════════════════════════════════╗
# ║  Part 2: Logging & Sanitization                 ║
# ╚══════════════════════════════════════════════════╝

_SENSITIVE_PATTERNS = [
    (re.compile(r"(password|passwd|pwd|secret|token|api[_-]?key|authorization)\s*[:=]\s*\S+", re.I), r"\1=***"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "***ID_CARD***"),
    (re.compile(r"\b(?:Bearer\s+)?[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\b"), "***JWT***"),
]


class _ContextFilter(logging.Filter):
    """Injects context variables into log records."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _ctx_trace_id.get() or "-"  # type: ignore
        record.user_id = _ctx_user_id.get() or "-"    # type: ignore
        return True


class _SanitizeFilter(logging.Filter):
    """Redacts sensitive information from log messages."""
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pattern, repl in _SENSITIVE_PATTERNS:
                msg = pattern.sub(repl, msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


_ctx_filter = _ContextFilter()
_sanitize_filter = _SanitizeFilter()


def _setup_logging(level: str = "INFO", *, rich: bool = True) -> logging.Logger:
    """Initialize good_addons logger."""
    logger = logging.getLogger("good_addons")
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addFilter(_ctx_filter)
    logger.addFilter(_sanitize_filter)

    if rich and _HAS_RICH and Console and RichHandler:
        console = Console(stderr=True)
        handler = RichHandler(console=console, show_time=True, show_path=False, markup=True, rich_tracebacks=True)
        handler.setFormatter(logging.Formatter("[dim]%(trace_id)s[/] %(message)s"))
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s │ %(levelname)-7s │ %(trace_id)s │ %(message)s", datefmt="%H:%M:%S"
        ))

    handler.addFilter(_ctx_filter)
    handler.addFilter(_sanitize_filter)
    logger.addHandler(handler)

    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.StreamHandler(sys.stderr))
    root.addFilter(_ctx_filter)
    root.addFilter(_sanitize_filter)

    return logger


log: logging.Logger = _setup_logging()


def get_logger(name: str = "") -> logging.Logger:
    """Get a logger with context and sanitization filters."""
    logger = logging.getLogger(name or "good_addons")
    logger.addFilter(_ctx_filter)
    logger.addFilter(_sanitize_filter)
    return logger


# ╔══════════════════════════════════════════════════╗
# ║  Part 3: Exception Fingerprinting               ║
# ╚══════════════════════════════════════════════════╝

class ExceptionFingerprinter:
    """Generates stable fingerprints for exceptions + deduplication."""

    _seen: Dict[str, float] = {}
    _lock = threading.Lock()
    _dedup_window: float = 60.0

    @staticmethod
    def fingerprint(exc: BaseException) -> str:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        normalized = [line.strip() for line in tb_lines if not line.startswith("  File ")]
        raw = f"{type(exc).__name__}:{exc}|{'|'.join(normalized[-3:])}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    @classmethod
    def capture(cls, exc: BaseException) -> Dict[str, Any]:
        fp = cls.fingerprint(exc)
        now = time.time()
        with cls._lock:
            last = cls._seen.get(fp, 0)
            if now - last < cls._dedup_window:
                return {"fingerprint": fp, "deduplicated": True}
            cls._seen[fp] = now
            if len(cls._seen) > 10000:
                cutoff = now - cls._dedup_window * 2
                cls._seen = {k: v for k, v in cls._seen.items() if v > cutoff}

        snapshot = RequestContext.snapshot()
        if 'AUDIT' in globals():
            globals()['AUDIT'].record("exception", details={
                "fingerprint": fp, "type": type(exc).__name__,
                "message": str(exc)[:500], "context": snapshot,
            })
        return {"fingerprint": fp, "deduplicated": False, "context": snapshot}


def _install_exception_hook() -> None:
    """Install global exception hook."""
    original_hook = sys.excepthook

    def _hook(exc_type: Type[BaseException], exc_value: BaseException, exc_tb: Any) -> None:
        try:
            info = ExceptionFingerprinter.capture(exc_value)
            if not info.get("deduplicated"):
                log.error(
                    "💥 Unhandled exception [%s] | ctx=%s",
                    info["fingerprint"], info.get("context"),
                    exc_info=(exc_type, exc_value, exc_tb),
                )
        except Exception:
            pass
        original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


# ╔══════════════════════════════════════════════════╗
# ║  Part 4: Decorator Arsenal                      ║
# ╚══════════════════════════════════════════════════╝

def _safe_repr(args: Any, kwargs: Any, max_len: int = 200) -> str:
    try:
        parts = [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
        res = ", ".join(parts)
        return res[:max_len] + "..." if len(res) > max_len else res
    except Exception:
        return "<repr failed>"


@overload
def trace(func: F) -> F: ...
@overload
def trace(*, level: int = logging.DEBUG, slow_ms: float = 200, log_args: bool = False, memory: bool = False, name: str = "") -> Callable[[F], F]: ...

def trace(
    _func: Optional[F] = None, *, level: int = logging.DEBUG, slow_ms: float = 200,
    log_args: bool = False, memory: bool = False, name: str = "",
) -> Union[F, Callable[[F], F]]:
    """Performance tracing decorator."""
    def decorator(func: F) -> F:
        fname = name or f"{func.__module__}.{func.__qualname__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            mem_before = psutil.Process().memory_info().rss if memory and _HAS_PSUTIL and psutil else 0
            tid = secrets.token_hex(4)
            old = _ctx_trace_id.set(_ctx_trace_id.get() or tid)
            _recorded = False
            try:
                if log_args:
                    log.log(level, "→ %s(%s)", fname, _safe_repr(args, kwargs))
                return await func(*args, **kwargs)
            except Exception:
                ms = (time.perf_counter() - t0) * 1000
                PERF.record(fname, ms, error=True)
                log.error("✗ %s FAILED %.1fms", fname, ms)
                _recorded = True
                raise
            finally:
                _ctx_trace_id.reset(old)
                if not _recorded:
                    ms = (time.perf_counter() - t0) * 1000
                    PERF.record(fname, ms)
                else:
                    ms = (time.perf_counter() - t0) * 1000
                if ms > slow_ms:
                    log.warning("⏱ SLOW %s: %.1fms (threshold: %.0fms)", fname, ms, slow_ms)
                if memory and _HAS_PSUTIL and psutil:
                    delta = psutil.Process().memory_info().rss - mem_before
                    if abs(delta) > 1024 * 1024:
                        log.info("🧠 %s mem Δ: %+.1fMB", fname, delta / (1024 * 1024))

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            t0 = time.perf_counter()
            mem_before = psutil.Process().memory_info().rss if memory and _HAS_PSUTIL and psutil else 0
            tid = secrets.token_hex(4)
            old = _ctx_trace_id.set(_ctx_trace_id.get() or tid)
            _recorded = False
            try:
                if log_args:
                    log.log(level, "→ %s(%s)", fname, _safe_repr(args, kwargs))
                return func(*args, **kwargs)
            except Exception:
                ms = (time.perf_counter() - t0) * 1000
                PERF.record(fname, ms, error=True)
                log.error("✗ %s FAILED %.1fms", fname, ms)
                _recorded = True
                raise
            finally:
                _ctx_trace_id.reset(old)
                if not _recorded:
                    ms = (time.perf_counter() - t0) * 1000
                    PERF.record(fname, ms)
                else:
                    ms = (time.perf_counter() - t0) * 1000
                if ms > slow_ms:
                    log.warning("⏱ SLOW %s: %.1fms (threshold: %.0fms)", fname, ms, slow_ms)
                if memory and _HAS_PSUTIL and psutil:
                    delta = psutil.Process().memory_info().rss - mem_before
                    if abs(delta) > 1024 * 1024:
                        log.info("🧠 %s mem Δ: %+.1fMB", fname, delta / (1024 * 1024))

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    if _func is not None:
        return decorator(_func)
    return decorator


@overload
def retry(func: F) -> F: ...
@overload
def retry(*, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0, exponential: bool = True, jitter: bool = True, exceptions: Tuple[Type[Exception], ...] = (Exception,), backoff_factor: float = 2.0) -> Callable[[F], F]: ...

def retry(
    _func: Optional[F] = None, *, max_attempts: int = 3, base_delay: float = 1.0,
    max_delay: float = 60.0, exponential: bool = True, jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,), backoff_factor: float = 2.0,
) -> Union[F, Callable[[F], F]]:
    """Retry decorator with exponential backoff."""
    def decorator(func: F) -> F:
        def _delay(attempt: int) -> float:
            d = base_delay * (backoff_factor ** (attempt - 1)) if exponential else base_delay
            d = min(d, max_delay)
            if jitter:
                d *= (0.5 + secrets.randbelow(100) / 100.0)
            return d

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        log.error("✗ %s failed after %d attempts: %s", func.__qualname__, max_attempts, e)
                        raise
                    delay = _delay(attempt)
                    log.warning("↻ %s attempt %d/%d failed (%s), retry in %.2fs", func.__qualname__, attempt, max_attempts, e, delay)
                    await asyncio.sleep(delay)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        log.error("✗ %s failed after %d attempts: %s", func.__qualname__, max_attempts, e)
                        raise
                    delay = _delay(attempt)
                    log.warning("↻ %s attempt %d/%d failed (%s), retry in %.2fs", func.__qualname__, attempt, max_attempts, e, delay)
                    time.sleep(delay)

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    if _func is not None:
        return decorator(_func)
    return decorator


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    """Circuit Breaker pattern implementation."""

    def __init__(
        self, failure_threshold: int = 5, recovery_timeout: float = 30.0,
        success_threshold: int = 2, fallback: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.fallback = fallback
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._last_fail_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN and (time.time() - self._last_fail_time >= self.recovery_timeout):
                self._state = CircuitState.HALF_OPEN
                self._successes = 0
                log.info("⚡ CircuitBreaker: OPEN → HALF_OPEN")
            return self._state

    def __call__(self, func: F) -> F:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.state == CircuitState.OPEN:
                if self.fallback:
                    return self.fallback(*args, **kwargs)
                raise CircuitOpenError(f"Circuit OPEN for {func.__qualname__}")
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception:
                self._on_failure()
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.state == CircuitState.OPEN:
                if self.fallback:
                    return self.fallback(*args, **kwargs)
                raise CircuitOpenError(f"Circuit OPEN for {func.__qualname__}")
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except Exception:
                self._on_failure()
                raise

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    def _on_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._state == CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    log.info("⚡ CircuitBreaker: HALF_OPEN → CLOSED")

    def _on_failure(self) -> None:
        with self._lock:
            self._failures += 1
            self._last_fail_time = time.time()
            if self._failures >= self.failure_threshold or self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                log.warning("⚡ CircuitBreaker: → OPEN (failures: %d)", self._failures)


@overload
def circuit_breaker(func: F) -> F: ...
@overload
def circuit_breaker(*, failure_threshold: int = 5, recovery_timeout: float = 30.0, fallback: Optional[Callable[..., Any]] = None) -> Callable[[F], F]: ...

def circuit_breaker(
    _func: Optional[F] = None, *, failure_threshold: int = 5,
    recovery_timeout: float = 30.0, fallback: Optional[Callable[..., Any]] = None,
) -> Union[F, Callable[[F], F]]:
    breaker = CircuitBreaker(failure_threshold, recovery_timeout, fallback=fallback)
    if _func is not None:
        return breaker(_func)
    return breaker


class _TokenBucket:
    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class RateLimitError(Exception):
    pass


def rate_limited(rate: float = 10.0, capacity: int = 20, *, on_limit: Optional[Callable[..., Any]] = None) -> Callable[[F], F]:
    bucket = _TokenBucket(rate, capacity)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not bucket.acquire():
                if on_limit:
                    return on_limit(*args, **kwargs)
                raise RateLimitError(f"Rate limit exceeded for {func.__qualname__}")
            return func(*args, **kwargs)
        return cast(F, wrapper)
    return decorator


def cached(ttl: float = 300, *, maxsize: int = 1024, key_func: Optional[Callable[..., str]] = None, jitter: float = 0.0) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        store: Dict[str, Tuple[Any, float]] = {}
        lock = threading.Lock()
        stats = {"hits": 0, "misses": 0, "evictions": 0}

        def _key(args: Any, kwargs: Any) -> str:
            if key_func:
                return key_func(*args, **kwargs)
            return hashlib.md5(str((func.__qualname__, repr(args), repr(sorted(kwargs.items())))).encode()).hexdigest()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _key(args, kwargs)
            now = time.time()
            with lock:
                if key in store and now < store[key][1]:
                    stats["hits"] += 1
                    return store[key][0]
                if len(store) >= maxsize:
                    oldest = min(store, key=lambda k: store[k][1])
                    del store[oldest]
                    stats["evictions"] += 1
            result = func(*args, **kwargs)
            actual_ttl = ttl + (secrets.randbelow(int(jitter * 1000)) / 1000.0 if jitter > 0 else 0)
            with lock:
                store[key] = (result, now + actual_ttl)
                stats["misses"] += 1
            return result

        wrapper.cache_clear = lambda: store.clear()  # type: ignore
        wrapper.cache_stats = lambda: dict(stats)    # type: ignore
        return cast(F, wrapper)
    return decorator


def memoize(func: F) -> F:
    cache: Dict[str, Any] = {}

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = hashlib.md5(str((func.__qualname__, repr(args), repr(sorted(kwargs.items())))).encode()).hexdigest()
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    wrapper.cache_clear = cache.clear  # type: ignore
    return cast(F, wrapper)


def validated(**type_hints: Any) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        if not _HAS_PYDANTIC or not type_hints:
            return func

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            for name, expected in type_hints.items():
                if name in bound.arguments and not isinstance(bound.arguments[name], expected):
                    try:
                        bound.arguments[name] = expected(bound.arguments[name])
                    except (ValueError, TypeError) as e:
                        raise TypeError(f"Param '{name}': expected {expected.__name__}, got {type(bound.arguments[name]).__name__} ({e})")
            return func(*bound.args, **bound.kwargs)
        return cast(F, wrapper)
    return decorator


@overload
def guarded(func: F) -> F: ...
@overload
def guarded(*, fallback: Any = None, catch: Tuple[Type[Exception], ...] = (Exception,), log_error: bool = True, reraise: bool = False) -> Callable[[F], F]: ...

def guarded(
    _func: Optional[F] = None, *, fallback: Any = None,
    catch: Tuple[Type[Exception], ...] = (Exception,), log_error: bool = True, reraise: bool = False,
) -> Union[F, Callable[[F], F]]:
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except catch as e:
                if log_error:
                    log.error("🛡 %s caught %s: %s", func.__qualname__, type(e).__name__, e, exc_info=True)
                if reraise:
                    raise
                return fallback() if callable(fallback) else fallback

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except catch as e:
                if log_error:
                    log.error("🛡 %s caught %s: %s", func.__qualname__, type(e).__name__, e, exc_info=True)
                if reraise:
                    raise
                return fallback() if callable(fallback) else fallback

        if inspect.iscoroutinefunction(func):
            return cast(F, async_wrapper)
        return cast(F, sync_wrapper)

    if _func is not None:
        return decorator(_func)
    return decorator


def debounce(wait: float = 0.3) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        timer: List[Optional[threading.Timer]] = [None]
        lock = threading.Lock()

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> None:
            with lock:
                if timer[0]:
                    timer[0].cancel()
                timer[0] = threading.Timer(wait, func, args=args, kwargs=kwargs)
                timer[0].start()
        return cast(F, wrapper)
    return decorator


# ╔══════════════════════════════════════════════════╗
# ║  Part 5: Security & System                      ║
# ╚══════════════════════════════════════════════════╝

class Security:
    """Security utilities."""
    _XSS = [
        re.compile(r"<script[^>]*>.*?</script>", re.I | re.S),
        re.compile(r"javascript\s*:", re.I),
        re.compile(r"on\w+\s*=", re.I),
    ]
    _SQL = re.compile(r"\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|TRUNCATE|--|;)\b", re.I)

    # --- v5.0: CSP Presets ---
    CSP_STRICT = "default-src 'self'"
    CSP_DASH_COMPAT = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-eval' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' ws: wss: https://dash-version.plotly.com;"
    )

    @staticmethod
    def sanitize_html(text: str) -> str:
        return html.escape(str(text), quote=True)

    @staticmethod
    def strip_xss(text: str) -> str:
        res = str(text)
        for p in Security._XSS:
            res = p.sub("", res)
        return res

    @staticmethod
    def detect_sql_injection(text: str) -> bool:
        return bool(Security._SQL.search(str(text)))

    @staticmethod
    def hash_password(password: str, *, salt: str = "") -> str:
        salt = salt or secrets.token_hex(16)
        return f"{salt}:{hashlib.sha256(f'{salt}{password}'.encode()).hexdigest()}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        try:
            salt, expected = hashed.split(":", 1)
            return secrets.compare_digest(hashlib.sha256(f"{salt}{password}".encode()).hexdigest(), expected)
        except ValueError:
            return False

    @staticmethod
    def encrypt(data: str, key: Optional[bytes] = None) -> Tuple[str, bytes]:
        if not _HAS_CRYPTO or not Fernet:
            raise ImportError("pip install cryptography")
        key = key or Fernet.generate_key()
        return Fernet(key).encrypt(data.encode()).decode(), key

    @staticmethod
    def decrypt(token: str, key: bytes) -> str:
        if not _HAS_CRYPTO or not Fernet:
            raise ImportError("pip install cryptography")
        return Fernet(key).decrypt(token.encode()).decode()

    @staticmethod
    def security_headers(csp: Optional[str] = None) -> Dict[str, str]:
        """Return security headers. Pass csp to override Content-Security-Policy."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": csp or Security.CSP_STRICT,
        }


class SystemMonitor:
    """System resource monitoring."""

    @staticmethod
    def memory_info() -> Dict[str, Any]:
        if _HAS_PSUTIL and psutil:
            mem = psutil.Process().memory_info()
            return {"rss_mb": round(mem.rss / 1048576, 2), "vms_mb": round(mem.vms / 1048576, 2)}
        return {}

    @staticmethod
    def start_memory_watchdog(
        *, max_mb: float = 2048, interval: float = 30, callback: Optional[Callable[..., Any]] = None,
    ) -> threading.Thread:
        def _watchdog() -> None:
            while True:
                time.sleep(interval)
                info = SystemMonitor.memory_info()
                if info.get("rss_mb", 0) > max_mb:
                    log.critical("🚨 Memory watchdog: %.0fMB > %.0fMB", info["rss_mb"], max_mb)
                    if callback:
                        callback(info)
                    EVENTS.emit("memory_critical", **info)

        t = threading.Thread(target=_watchdog, daemon=True, name="mem-watchdog")
        t.start()
        return t


class AuditLog(metaclass=_SingletonMeta):
    """Audit log collector."""

    def __init__(self, *, max_entries: int = 10000) -> None:
        self._entries: deque[Dict[str, Any]] = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def record(self, action: str, *, actor: str = "", resource: str = "", details: Any = None) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor or RequestContext.user_id() or "system",
            "trace_id": RequestContext.trace_id(),
            "resource": resource,
            "details": details,
        }
        with self._lock:
            self._entries.append(entry)
        return entry

    def query(self, *, action: str = "", actor: str = "", last_n: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            entries = list(self._entries)
        if action:
            entries = [e for e in entries if e["action"] == action]
        if actor:
            entries = [e for e in entries if e["actor"] == actor]
        return entries[-last_n:]


class MetricsCollector(metaclass=_SingletonMeta):
    """Metrics collector with optional Prometheus integration."""

    def __init__(self) -> None:
        self._counters: Dict[str, Any] = {}
        self._simple: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def counter(self, name: str) -> None:
        with self._lock:
            self._simple[name] += 1
            if _HAS_PROMETHEUS and prometheus_client:
                if name not in self._counters:
                    self._counters[name] = prometheus_client.Counter(name, f"Counter: {name}")
                self._counters[name].inc()

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._simple)


class GracefulShutdown(metaclass=_SingletonMeta):
    """Graceful shutdown manager."""

    def __init__(self) -> None:
        self._handlers: List[Tuple[int, Callable[..., Any]]] = []
        self._event = threading.Event()
        self._installed = False

    def register(self, handler: Callable[..., Any], *, priority: int = 0) -> None:
        self._handlers.append((priority, handler))
        self._handlers.sort(key=lambda x: -x[0])

    def install(self) -> None:
        if self._installed or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            return
        self._installed = True

        def _handler(signum: int, frame: Any) -> None:
            log.info("🛑 Received signal %s, shutting down...", signal.Signals(signum).name)
            self._event.set()
            for _, h in self._handlers:
                try:
                    h()
                except Exception as e:
                    log.error("Shutdown handler error: %s", e)
            sys.exit(0)

        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout)


# ╔══════════════════════════════════════════════════╗
# ║  Part 6: JSON & Web Enhancement  (v5.0 rewrite) ║
# ╚══════════════════════════════════════════════════╝

def fast_json_dumps(obj: Any, *, pretty: bool = False) -> str:
    if _HAS_ORJSON and orjson:
        opts = orjson.OPT_NON_STR_KEYS | (orjson.OPT_INDENT_2 if pretty else 0)
        return orjson.dumps(obj, option=opts).decode()
    return json.dumps(obj, default=str, ensure_ascii=False, indent=2 if pretty else None)


def fast_json_loads(data: Union[str, bytes]) -> Any:
    if _HAS_ORJSON and orjson:
        return orjson.loads(data.encode() if isinstance(data, str) else data)
    return json.loads(data)


def _is_dash_app(app: Any) -> bool:
    """Detect if app is a Dash application."""
    cls_name = type(app).__name__
    if cls_name == "Dash":
        return True
    for base in type(app).__mro__:
        if base.__name__ == "Dash":
            return True
    # Also check if app has .server (Dash wraps Flask)
    server = getattr(app, "server", None)
    if server is not None and hasattr(server, "after_request"):
        # Could be Dash — check for dash-specific attributes
        if hasattr(app, "layout") or hasattr(app, "callback_map"):
            return True
    return False


def _enhance_web_app(app: Any, csp_policy: Optional[str] = None) -> None:
    """
    v5.0: Enhance Flask/Dash app with security, tracing, and error handling.

    Key improvements over v4.0:
      - Auto-detects Dash and applies compatible CSP (no more blocked scripts)
      - Logs ALL requests (not just slow ones) with status code coloring
      - Errors always print full traceback to stderr + return JSON to client
      - Dash callback errors are caught and logged with full context
      - Enhancement failures produce detailed diagnostics
    """
    is_dash = _is_dash_app(app)
    framework = "Dash" if is_dash else "Flask"

    # Determine CSP: explicit > auto-detect > strict
    effective_csp: str
    if csp_policy is not None:
        effective_csp = csp_policy
    elif is_dash:
        effective_csp = Security.CSP_DASH_COMPAT
    else:
        effective_csp = Security.CSP_STRICT

    try:
        server = getattr(app, "server", app)

        # ── Hook 1: Security Headers + Request Context ──
        @server.after_request
        def add_headers(response: Any) -> Any:
            headers = Security.security_headers(csp=effective_csp)
            for k, v in headers.items():
                response.headers[k] = v
            response.headers["X-Request-ID"] = RequestContext.trace_id()
            response.headers["X-Response-Time"] = f"{RequestContext.elapsed() * 1000:.1f}ms"
            return response

        # ── Hook 2: Trace ID + Timer ──
        @server.before_request
        def trace_req() -> None:
            _ctx_trace_id.set(secrets.token_hex(8))
            _ctx_request_start.set(time.perf_counter())

        # ── Hook 3: Request Logging (v5.0: ALL requests, colored) ──
        @server.after_request
        def log_req(response: Any) -> Any:
            ms = RequestContext.elapsed() * 1000
            try:
                from flask import request
                method = request.method
                path = request.path
                status = response.status_code

                # Skip noisy static/asset requests in non-debug
                if path.startswith("/_dash-component-suites/") or path.startswith("/assets/"):
                    if status >= 400:
                        log.warning("🌐 %s %s → %d (%.0fms)", method, path, status, ms)
                    return response

                # Color by status code
                if status >= 500:
                    log.error("🌐 %s %s → %d (%.0fms) 🔴", method, path, status, ms)
                elif status >= 400:
                    log.warning("🌐 %s %s → %d (%.0fms) 🟡", method, path, status, ms)
                elif ms > 500:
                    log.warning("🌐 %s %s → %d (%.0fms) 🐢", method, path, status, ms)
                else:
                    log.info("🌐 %s %s → %d (%.0fms)", method, path, status, ms)
            except ImportError:
                pass
            return response

        # ── Hook 4: Error Handler (v5.0: always log full traceback) ──
        @server.errorhandler(Exception)
        def handle_error(exc: Exception) -> Any:
            status = getattr(exc, "code", 500)
            if not isinstance(status, int) or status < 400:
                status = 500

            info = ExceptionFingerprinter.capture(exc)
            tid = RequestContext.trace_id()

            # ★ v5.0: ALWAYS log full traceback to backend stderr
            log.error(
                "💥 HTTP %d | %s: %s | request_id=%s | fingerprint=%s",
                status, type(exc).__name__, exc, tid, info.get("fingerprint"),
                exc_info=True,
            )

            try:
                from flask import jsonify
                return jsonify({
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc) if status < 500 else "Internal Server Error",
                        "request_id": tid,
                        "fingerprint": info.get("fingerprint"),
                        "hint": f"Check server logs for request_id={tid}",
                    }
                }), status
            except ImportError:
                raise exc

        # ── v5.0: Dash callback error wrapping ──
        if is_dash:
            _wrap_dash_callbacks(app)

        log.info(
            "✅ Web app enhanced [%s] | CSP: %s | hooks: headers, trace, logging, errors%s",
            framework,
            effective_csp[:60] + ("..." if len(effective_csp) > 60 else ""),
            ", callback-wrapping" if is_dash else "",
        )

    except Exception as e:
        # ★ v5.0: Detailed diagnostic instead of silent warning
        log.error(
            "❌ Web enhancement FAILED for %s app: %s\n"
            "   app type: %s\n"
            "   server attr: %s\n"
            "   csp_policy: %s",
            framework, e,
            type(app).__name__,
            type(getattr(app, "server", None)).__name__,
            effective_csp[:80],
            exc_info=True,
        )


def _wrap_dash_callbacks(app: Any) -> None:
    """
    v5.0: Wrap Dash callbacks to catch unhandled exceptions and log them
    with full traceback + context, instead of just showing a red error
    box in the browser with no backend log.
    """
    try:
        callback_map = getattr(app, "callback_map", None)
        if not callback_map:
            log.debug("No callback_map found, skipping callback wrapping")
            return

        wrapped_count = 0
        for output_key, cb_info in callback_map.items():
            original_func = cb_info.get("callback")
            if original_func is None:
                continue

            @functools.wraps(original_func)
            def _make_wrapper(orig: Any) -> Any:
                def wrapper(*args: Any, **kwargs: Any) -> Any:
                    try:
                        return orig(*args, **kwargs)
                    except Exception as exc:
                        info = ExceptionFingerprinter.capture(exc)
                        tid = RequestContext.trace_id()
                        log.error(
                            "💥 Dash callback error | %s: %s | request_id=%s | fingerprint=%s",
                            type(exc).__name__, exc, tid, info.get("fingerprint"),
                            exc_info=True,
                        )
                        raise  # Re-raise so Dash's own error handling still works
                return wrapper

            cb_info["callback"] = _make_wrapper(original_func)
            wrapped_count += 1

        if wrapped_count > 0:
            log.info("🔗 Wrapped %d Dash callbacks with error logging", wrapped_count)

    except Exception as e:
        log.warning(
            "⚠️ Dash callback wrapping failed (non-fatal): %s\n"
            "   Callbacks will still work, but unhandled errors won't be logged with full context.",
            e, exc_info=True,
        )


# ╔══════════════════════════════════════════════════╗
# ║  Part 7: Global Singletons & Bootstrap          ║
# ╚══════════════════════════════════════════════════╝

PERF = PerformanceMonitor()
EVENTS = EventBus()
METRICS = MetricsCollector()
AUDIT = AuditLog()
SHUTDOWN = GracefulShutdown()
SYSTEM = SystemMonitor()

_boost_initialized = False


def boost(
    app: Any = None,
    *,
    log_level: str = "INFO",
    memory_watchdog: bool = False,
    memory_limit_mb: float = 2048,
    graceful_shutdown: bool = True,
    rich_logging: bool = True,
    sanitize_logs: bool = True,
    exception_fingerprint: bool = True,
    csp_policy: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Bootstrap the runtime enhancement layer.

    v5.0:
      - Dash apps automatically get CSP_DASH_COMPAT (unless csp_policy is explicit)
      - All requests logged (not just slow ones)
      - Errors always produce full backend traceback
      - New: diag() for quick diagnostics
    """
    global log, _boost_initialized

    if _boost_initialized:
        log.debug("boost() already initialized, skipping")
        return {
            "_skipped": True,
            "log": log,
            "perf": PERF,
            "events": EVENTS,
            "audit": AUDIT,
            "shutdown": SHUTDOWN,
        }

    log = _setup_logging(level=log_level, rich=rich_logging)
    log.info("🚀 good_addons v%s bootstrapping...", __version__)

    if graceful_shutdown:
        SHUTDOWN.install()
    if memory_watchdog:
        SYSTEM.start_memory_watchdog(max_mb=memory_limit_mb)
    if exception_fingerprint:
        _install_exception_hook()
    if app:
        _enhance_web_app(app, csp_policy=csp_policy)

    _boost_initialized = True

    deps = [
        n for n, f in [
            ("rich", _HAS_RICH),
            ("psutil", _HAS_PSUTIL),
            ("orjson", _HAS_ORJSON),
            ("pydantic", _HAS_PYDANTIC),
            ("prometheus", _HAS_PROMETHEUS),
            ("crypto", _HAS_CRYPTO),
        ] if f
    ]
    log.info(
        "✅ boost() complete | deps: %s | pid: %d",
        ", ".join(deps) or "stdlib",
        os.getpid(),
    )

    return {
        "_skipped": False,
        "log": log,
        "perf": PERF,
        "events": EVENTS,
        "audit": AUDIT,
        "shutdown": SHUTDOWN,
        "system": SYSTEM,
        "security": Security,
    }


# ╔══════════════════════════════════════════════════╗
# ║  Part 8: Diagnostics (v5.0 NEW)                 ║
# ╚══════════════════════════════════════════════════╝

def diag(*, perf_top: int = 15, audit_last: int = 20) -> str:
    """
    Quick diagnostic dump — call this from a debug endpoint or REPL
    to get a snapshot of everything good_addons has collected.

    Returns formatted string with:
      - Performance stats (top N slowest functions)
      - Recent audit entries
      - System memory
      - Metrics counters
    """
    sections: List[str] = []

    # Performance
    sections.append("═══ Performance ═══")
    sections.append(PERF.format_table(top_n=perf_top))

    # Audit
    sections.append("\n═══ Recent Audit ═══")
    entries = AUDIT.query(last_n=audit_last)
    if entries:
        for e in entries:
            ts = e["timestamp"][:19]
            sections.append(f"  {ts} | {e['action']:<20} | {e['actor']:<15} | {str(e.get('details', ''))[:80]}")
    else:
        sections.append("  (empty)")

    # System
    sections.append("\n═══ System ═══")
    mem = SystemMonitor.memory_info()
    if mem:
        sections.append(f"  RSS: {mem['rss_mb']:.1f} MB | VMS: {mem['vms_mb']:.1f} MB")
    else:
        sections.append("  (psutil not available)")

    # Metrics
    sections.append("\n═══ Metrics ═══")
    metrics = METRICS.snapshot()
    if metrics:
        for k, v in sorted(metrics.items()):
            sections.append(f"  {k}: {v:.0f}")
    else:
        sections.append("  (empty)")

    # EventBus history
    sections.append("\n═══ Recent Events ═══")
    recent = list(EVENTS._history)[-10:]
    if recent:
        for e in recent:
            ts = datetime.fromtimestamp(e["time"], tz=timezone.utc).strftime("%H:%M:%S")
            sections.append(f"  {ts} | {e['event']:<25} | seq={e['seq']}")
    else:
        sections.append("  (empty)")

    output = "\n".join(sections)
    log.info("📊 Diagnostic dump:\n%s", output)
    return output
