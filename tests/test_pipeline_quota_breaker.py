"""The quota circuit breaker: a hard-out-of-usage provider pauses the run.

Retries outlast TRANSPORT problems; a session-usage-limit 429 only clears
when the provider's window resets, so retries just waste minutes per
candidate. The breaker counts consecutive quota-killed dives, stops the run
loudly at the second, and lets in-flight ladders bail fast so a rerun after
the reset resumes cheaply from the caches.
"""


def test_quota_stop_bails_out_of_the_ladder_immediately():
    """An already-set quota stop: one attempt, zero sleeps, loud failure."""
    from threading import Event

    from ptm.pipeline import run_deep_dive_with_retries

    calls, sleeps = [], []
    stop = Event()
    stop.set()  # the breaker has already tripped elsewhere in the run

    def fake_dive(ticker, **kw):
        calls.append(ticker)
        raise type("Q", (Exception,), {"status_code": 402})("you have reached your session usage limit")

    import ptm.pipeline as pl

    orig = pl.run_deep_dive
    pl.run_deep_dive = fake_dive
    try:
        try:
            run_deep_dive_with_retries("ABCD", sleeper=sleeps.append, quota_stop=stop)
            raised = False
        except Exception:
            raised = True
    finally:
        pl.run_deep_dive = orig
    assert raised
    assert len(calls) == 1, "a set quota stop must abort after the current attempt"
    assert sleeps == [], "no waiting when the breaker is already tripped"


def test_quota_breaker_trips_on_two_consecutive_quota_failures():
    from threading import Event

    from ptm.pipeline import _quota_strike

    strikes, stop = {"n": 0}, Event()
    quota = type("Q", (Exception,), {"status_code": 402})()
    flaky = RuntimeError("connection reset")

    _strike = __import__("ptm.pipeline", fromlist=["_quota_strike"])._quota_strike
    _strike(strikes, flaky, stop)
    _strike(strikes, quota, stop)
    assert not stop.is_set() and strikes["n"] == 1  # one strike from a flaky name: keep retrying
    _strike(strikes, quota, stop)
    assert stop.is_set(), "two quota kills in a row = the session is out of usage"
    assert strikes["n"] == 2
    _strike(strikes, flaky, stop)  # a non-quota failure never UN-sets a tripped breaker
    assert stop.is_set()


def test_quota_breaker_counts_rate_limited_error_results():
    """A sustained 429 storm arrives as error RESULTS, not exceptions — the
    breaker must see them, or a whole run grinds through 100+ failed dives
    on 20s ladders (which is exactly what happened on 2026-08-30)."""
    from threading import Event

    from ptm.pipeline import _quota_strike, note_incomplete_dive

    strikes, stop = {"n": 0}, Event()
    throttled = RuntimeError("dive incomplete: web search rate-limited (HTTP 429)")
    registry: list[dict] = []

    _strike = __import__("ptm.pipeline", fromlist=["_quota_strike"])._quota_strike
    note_incomplete_dive({"ticker": "AAA", "reason": throttled.args[0]}, registry)
    _strike(strikes, throttled, stop)
    assert not stop.is_set(), "one throttled dive still gets its ladder"
    note_incomplete_dive({"ticker": "BBB", "reason": throttled.args[0]}, registry)
    _strike(strikes, throttled, stop)
    assert stop.is_set(), "two rate-limited dives in a row = the run is throttled"
    assert [d["ticker"] for d in registry] == ["AAA", "BBB"]


def test_registry_note_dedupes():
    from ptm.pipeline import note_incomplete_dive

    sink: list[dict] = []
    note_incomplete_dive({"ticker": "AAA", "reason": "x"}, sink)
    note_incomplete_dive({"ticker": "AAA", "reason": "x"}, sink)
    assert len(sink) == 1