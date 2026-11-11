"""
Stage timing for graph construction.

A process-wide registry that accumulates wall time, call counts, and arbitrary
counters (bytes downloaded, LLM tokens, ...) per named stage, so that network-bound
stages (metadata API queries, file download, LLM calls) can be reported separately
from local processing (parsing, grounding, graph extraction).

Usage::

    from dglink.core.timing import TIMER

    with TIMER.stage("download"):
        path = syn.get(...)
    TIMER.add("download", bytes=os.path.getsize(path), files=1)

    TIMER.write_report("timing.json")

Stages nest freely; each stage records its own wall time, so a parent stage's time
includes its children (e.g. ``tabular`` includes ``tabular.grounding``).
"""

from collections import defaultdict
from contextlib import contextmanager
import json
import os
import platform
import statistics
import time
from datetime import datetime, timezone


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1]


class StageTimer:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.durations: dict[str, list[float]] = defaultdict(list)
        self.counters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.started_at = datetime.now(timezone.utc).isoformat()
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str):
        """Time the enclosed block and record it under ``name``."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.durations[name].append(time.perf_counter() - t0)

    def record(self, name: str, seconds: float) -> None:
        """Record an externally measured duration for ``name``."""
        self.durations[name].append(seconds)

    def add(self, name: str, **counts: float) -> None:
        """Increment counters for ``name``, e.g. ``add("download", bytes=n, files=1)``."""
        for key, val in counts.items():
            if val is not None:
                self.counters[name][key] += val

    def summary(self) -> dict:
        names = sorted(set(self.durations) | set(self.counters))
        stages = {}
        for name in names:
            d = self.durations.get(name, [])
            stages[name] = {
                "total_seconds": round(sum(d), 3),
                "calls": len(d),
                "median_seconds": round(statistics.median(d), 4) if d else 0.0,
                "p95_seconds": round(_percentile(d, 95), 4),
                **{k: v for k, v in self.counters.get(name, {}).items()},
            }
        return {
            "started_at": self.started_at,
            "wall_seconds": round(time.perf_counter() - self._t0, 3),
            "host": platform.node(),
            "cpu_count": os.cpu_count(),
            "stages": stages,
        }

    def write_report(self, path: str, **extra) -> dict:
        report = {**self.summary(), **extra}
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        return report

    def print_summary(self) -> None:
        s = self.summary()
        print(f"\nTiming (wall {s['wall_seconds']:,.1f}s)")
        for name, st in s["stages"].items():
            extras = {
                k: v
                for k, v in st.items()
                if k not in ("total_seconds", "calls", "median_seconds", "p95_seconds")
            }
            extra_str = "  " + ", ".join(f"{k}={v:,.0f}" for k, v in extras.items()) if extras else ""
            print(
                f"  {name:<32} {st['total_seconds']:>10,.1f}s  "
                f"calls={st['calls']:<6} median={st['median_seconds']:.3f}s "
                f"p95={st['p95_seconds']:.3f}s{extra_str}"
            )


## process-wide timer
TIMER = StageTimer()
