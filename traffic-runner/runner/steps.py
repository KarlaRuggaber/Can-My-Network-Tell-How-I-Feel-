"""Time limits for single browser steps, sharing SIGALRM with the run's watchdog (since 26.10).

25.10: a Reddit page stuck in its JS challenge (a busy main thread) blocked every Playwright
call of the run until the watchdog fired at the planned end + 90 s. Tested in a runner
container with a page running `while(true){}`: once one call hangs, every later call of that
Playwright instance hangs too (evaluate, new page, page/context/browser close, even a new
launch); only `Playwright.stop()` returns, and a new Playwright instance works again.

So every step gets a limit (Guard.limit); a step that exceeds it raises StepTimeout, and the
RunContext restarts Playwright and marks the site as hung for the rest of the block. The
watchdog keeps priority: if its deadline has passed when the alarm fires, Aborted is raised.
"""

from __future__ import annotations

import os
import signal
import time
from contextlib import contextmanager

from .context import StepTimeout


class Aborted(BaseException):
    """SIGTERM or watchdog. BaseException so no `except Exception` inside a driver eats it."""


class Guard:
    """One real-time alarm for both the watchdog (absolute deadline) and the current step."""

    def __init__(self, deadline: float | None, clock=time.monotonic):
        self.deadline = deadline  # clock() value at which the run is aborted, None = no watchdog
        self.clock = clock
        self.step: str | None = None

    def install(self) -> None:
        signal.signal(signal.SIGALRM, self._fire)
        self._arm_watchdog()

    def disarm(self) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)

    def _left(self) -> float | None:
        return None if self.deadline is None else self.deadline - self.clock()

    def _arm_watchdog(self) -> None:
        left = self._left()
        if left is None:
            self.disarm()
        else:
            signal.setitimer(signal.ITIMER_REAL, max(0.01, left))

    def _fire(self, signum, frame):
        left = self._left()
        if left is not None and left <= 0.05:
            raise Aborted("watchdog: deadline exceeded")
        raise StepTimeout(f"{self.step or 'browser step'} did not finish in time")

    @contextmanager
    def limit(self, seconds: float, what: str):
        """Run the block with a time limit; the watchdog still fires first if it comes earlier."""
        left = self._left()
        due = seconds if left is None else min(seconds, left)
        self.step = what
        signal.setitimer(signal.ITIMER_REAL, max(0.01, due))
        try:
            yield
        finally:
            self.step = None
            self._arm_watchdog()


# --- process tree ------------------------------------------------------------------------------
# Chromium does not run in the runner's process group (Playwright starts it in its own), so
# leftovers are found through the parent links in /proc.

def descendants(pid: int | None = None) -> list[int]:
    """All processes below `pid` (default: this process), children first. Empty without /proc."""
    pid = os.getpid() if pid is None else pid
    parent: dict[int, int] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    for e in entries:
        if not e.isdigit():
            continue
        try:
            with open(f"/proc/{e}/stat", "rb") as f:
                stat = f.read().decode(errors="replace")
            parent[int(e)] = int(stat.rsplit(")", 1)[1].split()[1])  # field 4: ppid
        except (OSError, ValueError, IndexError):
            continue
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        kids = [c for c, pp in parent.items() if pp == p]
        out.extend(kids)
        todo.extend(kids)
    return out


def kill_descendants(pid: int | None = None) -> int:
    """SIGKILL every process below `pid`; returns how many were signalled."""
    n = 0
    for p in reversed(descendants(pid)):
        try:
            os.kill(p, signal.SIGKILL)
            n += 1
        except OSError:
            pass
    return n
