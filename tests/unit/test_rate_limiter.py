from nexaro_core.security import RateLimiter


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make(clock: Clock, max_keys: int = 100) -> RateLimiter:
    return RateLimiter(max_attempts=3, window_seconds=60, max_keys=max_keys, clock=clock)


def test_limits_after_max_attempts_and_recovers_after_window() -> None:
    clock = Clock()
    limiter = make(clock)
    for _ in range(3):
        assert not limiter.is_limited("k")
        limiter.record("k")
    assert limiter.is_limited("k")

    clock.now += 61
    assert not limiter.is_limited("k")


def test_keys_are_independent_and_clear_resets_one() -> None:
    limiter = make(Clock())
    for _ in range(3):
        limiter.record("a")
    assert limiter.is_limited("a") and not limiter.is_limited("b")
    limiter.clear("a")
    assert not limiter.is_limited("a")


def test_memory_is_bounded_and_evicts_stale_first() -> None:
    clock = Clock()
    limiter = make(clock, max_keys=3)
    limiter.record("old")
    clock.now += 61  # 'old' caduca
    for key in ("a", "b", "c"):
        limiter.record(key)
    assert limiter.tracked_keys() <= 3
    assert not limiter.is_limited("old")


def test_oldest_key_is_evicted_when_all_are_recent() -> None:
    clock = Clock()
    limiter = make(clock, max_keys=2)
    limiter.record("first")
    clock.now += 1
    limiter.record("second")
    clock.now += 1
    limiter.record("third")
    assert limiter.tracked_keys() == 2
