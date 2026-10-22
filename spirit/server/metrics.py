"""Lightweight, dependency-free process metrics.
"""
import time
import asyncio
import logging
from typing import Callable

_counters: dict[str, int] = {}
_gauges: dict[str, Callable] = {}

# Event-loop lag ring buffer (ms), filled by sample_loop_lag().
_lag_samples: list[float] = []
_LAG_WINDOW = 300  # ~5 min at 1 Hz


def inc(name: str, amount: int = 1) -> None:
    _counters[name] = _counters.get(name, 0) + amount


def register_gauge(name: str, fn) -> None:
    """Registers a zero-arg callable read at scrape time (controlled cardinality)."""
    _gauges[name] = fn


def _lag_stats() -> dict:
    if not _lag_samples:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(_lag_samples)
    n = len(ordered)

    def pct(p):
        return round(ordered[min(n - 1, int(p * n))], 3)

    return {
        "count": n,
        "p50_ms": pct(0.50),
        "p95_ms": pct(0.95),
        "p99_ms": pct(0.99),
        "max_ms": round(ordered[-1], 3),
    }


def snapshot() -> dict:
    """Point-in-time view of all counters, gauges, and loop-lag stats."""
    gauges = {}
    for name, fn in _gauges.items():
        try:
            gauges[name] = fn()
        except Exception:
            gauges[name] = None
    return {
        "ts": time.time(),
        "counters": dict(_counters),
        "gauges": gauges,
        "event_loop_lag": _lag_stats(),
    }


async def sample_loop_lag(interval: float = 1.0):
    """Sleeps `interval` and records how much longer than `interval` it actually
    took — the classic asyncio starvation probe. Never raises out of the loop."""
    while True:
        start = time.perf_counter()
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # defensive: keep the sampler alive
            logging.debug(f"[Metrics] lag sampler hiccup: {e}")
            continue
        lag_ms = max(0.0, (time.perf_counter() - start - interval) * 1000.0)
        _lag_samples.append(lag_ms)
        if len(_lag_samples) > _LAG_WINDOW:
            del _lag_samples[0]


# ---------------------------------------------------------------------------
# Event-loop stall watchdog.
#
# Every connected client pings the server; if the asyncio loop is blocked for
# a few seconds those pings go unanswered and every client drops at once
# ("The network connection with the server has been lost").  The lag sampler
# above only reports that a stall happened.  This watchdog runs on its own
# thread, so while the loop is still stuck it logs WHAT the loop thread is
# executing, plus a one-line summary of every other busy thread.
# ---------------------------------------------------------------------------
import sys
import threading
import traceback

_STALL_THRESHOLD_S = 1.0
_heartbeat = [time.monotonic()]


async def _beat():
    while True:
        _heartbeat[0] = time.monotonic()
        await asyncio.sleep(0.2)


def _thread_summary(frames, skip):
    lines = []
    names = {t.ident: t.name for t in threading.enumerate()}
    for ident, frame in frames.items():
        if ident in skip:
            continue
        stack = traceback.extract_stack(frame)
        top = next((f for f in reversed(stack) if "/spirit/" in f.filename.replace("\\", "/")), stack[-1])
        lines.append(f"    {names.get(ident, ident)}: {top.filename.rsplit('/', 1)[-1]}:{top.lineno} {top.name}")
    return lines


def _watch(loop_ident, threshold):
    own = threading.get_ident()
    reported = False
    stall_start = None
    while True:
        time.sleep(0.25)
        idle = time.monotonic() - _heartbeat[0]
        if idle < threshold:
            if reported:
                logging.warning("[Watchdog] Event loop recovered after %.1fs stall.",
                                time.monotonic() - stall_start)
            reported = False
            stall_start = None
            continue
        if reported:
            continue
        reported = True
        stall_start = _heartbeat[0]
        try:
            frames = sys._current_frames()
            loop_frame = frames.get(loop_ident)
            stack = "".join(traceback.format_stack(loop_frame)[-12:]) if loop_frame else "?"
            others = _thread_summary(frames, {loop_ident, own})
            logging.warning(
                "[Watchdog] Event loop blocked for %.1fs. Loop thread is in:\n%s"
                "  Other threads:\n%s", idle, stack, "\n".join(others) or "    (none)")
        except Exception as e:  # never let the watchdog die
            logging.warning(f"[Watchdog] Event loop blocked for {idle:.1f}s (stack unavailable: {e})")


def start_stall_watchdog(threshold: float = _STALL_THRESHOLD_S):
    """Call from inside the running event loop. Returns the heartbeat task."""
    task = asyncio.ensure_future(_beat())
    threading.Thread(target=_watch, args=(threading.get_ident(), threshold),
                     name="loop-watchdog", daemon=True).start()
    return task
