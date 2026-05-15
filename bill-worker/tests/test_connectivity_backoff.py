import sys
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
WORKER_ROOT = THIS_DIR.parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

import main as worker_main  # noqa: E402


def test_backoff_failure_count_1_is_safe_and_bounded():
    tracker = worker_main.CoreConnectivityTracker(max_backoff_seconds=60.0, max_exponential_failures=10)

    backoff = tracker._compute_backoff(1)

    assert backoff == 1.0
    assert backoff <= tracker.max_backoff_seconds


def test_backoff_failure_count_10_is_safe_and_bounded():
    tracker = worker_main.CoreConnectivityTracker(max_backoff_seconds=60.0, max_exponential_failures=10)

    backoff = tracker._compute_backoff(10)

    assert backoff == 60.0
    assert backoff <= tracker.max_backoff_seconds


def test_backoff_failure_count_1000_does_not_overflow_and_is_bounded():
    tracker = worker_main.CoreConnectivityTracker(max_backoff_seconds=60.0, max_exponential_failures=10)

    backoff = tracker._compute_backoff(1000)

    assert backoff == 60.0
    assert backoff <= tracker.max_backoff_seconds


def test_jittered_delay_stays_within_max_backoff_cap(monkeypatch):
    tracker = worker_main.CoreConnectivityTracker(max_backoff_seconds=60.0, max_exponential_failures=10)

    # Force deterministic max jitter path.
    monkeypatch.setattr(worker_main.random, "uniform", lambda _a, b: b)

    delay = tracker.note_failure("register", RuntimeError("boom"))

    assert delay <= tracker.max_backoff_seconds

    for _ in range(1000):
        delay = tracker.note_failure("register", RuntimeError("boom"))

    assert tracker.current_backoff() <= tracker.max_backoff_seconds
    assert delay <= tracker.max_backoff_seconds
