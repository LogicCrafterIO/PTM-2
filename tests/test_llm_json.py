import json
from datetime import datetime, timedelta, timezone

import pytest

from ptm.llm import _extract_json, filter_non_earnings, qualitative, sanitize_kpis
from ptm.models import Candidate, Side


def test_extract_plain_object():
    assert _extract_json('{"markdown": "ok"}') == {"markdown": "ok"}


def test_extract_markdown_fence():
    blob = "```json\n{\"markdown\": \"# LONG X\"}\n```"
    assert _extract_json(blob)["markdown"] == "# LONG X"


def test_extract_trailing_junk():
    blob = '{"markdown": "ok"}\nHere is extra prose'
    assert _extract_json(blob)["markdown"] == "ok"


def test_extract_control_characters():
    blob = '{"markdown": "line1\x00line2"}'
    payload = _extract_json(blob)
    assert "line1" in payload["markdown"]


def test_extract_first_object_when_two_present():
    blob = '{"a": 1}\n{"b": 2}'
    assert _extract_json(blob) == {"a": 1}


def test_extract_no_object_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json("not json at all")


def test_filter_non_earnings_keeps_dated_events():
    dated = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    kept = filter_non_earnings(
        [
            "Has Arcosa Outpaced Other Construction Stocks This Year?",
            {"event": "Investor day", "date": dated, "why": "guidance update"},
            "Loss ratio 55.1 % 53.1 % 2.0 | Combined ratio dump",
            "Undated rumor with no calendar",
        ]
    )
    assert any("Investor day" in item for item in kept)
    assert not any("Outpaced" in item for item in kept)
    assert not any("Combined" in item for item in kept)


def test_sanitize_kpis_drops_statement_lines():
    cleaned, stripped = sanitize_kpis(
        ["revenue", "backlog", "net_income", "utilization", "IoT connectivity"]
    )
    assert cleaned == ["backlog", "utilization"]
    assert stripped is True


def test_mission_statement_is_not_an_operating_plan():
    from ptm.llm import sanitize_operating_plan

    plan, stripped = sanitize_operating_plan(
        "Enabling a smarter, more sustainable planet through connected products"
    )
    assert plan == ""
    assert stripped is True
    concrete, stripped = sanitize_operating_plan(
        "Expand manufacturing capacity and launch the new platform in fiscal 2027"
    )
    assert concrete
    assert stripped is False


def test_quant_screen_metrics_are_removed_from_qualitative_evidence():
    from ptm.llm import _strip_screen_evidence
    from ptm.models import EvidenceItem

    kept, stripped = _strip_screen_evidence(
        [
            EvidenceItem(claim="Strong forward EPS growth", metric="FY1 EPS growth"),
            EvidenceItem(
                claim="Backlog grew 22%",
                metric="Backlog growth",
                impact_pct=22.0,
                impact_on="revenue",
                quantified=True,
            ),
        ]
    )
    assert [item.claim for item in kept] == ["Backlog grew 22%"]
    assert stripped == 1


def test_qualitative_two_pass_uses_verdict_why(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    calls: list[str] = []

    def fake_chat(system: str, user: str, **kwargs):
        calls.append(system)
        if "Extract operating facts" in system:
            return {
                "business_in_one_line": "Makes HVAC equipment",
                "operating_plan": "Grow data-center backlog",
                "kpis": ["backlog", "revenue"],
                "red_flags": [],
                "ism_link": "Machinery growth",
                "quotes": ["backlog rose to a record"],
            }
        return {
            "supports_outlier": True,
            "why": "Backlog growth supports paying a premium for acceleration.",
            "denial_reason": "",
        }

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    result = qualitative(
        Candidate(ticker="X", side=Side.LONG, eg_case="long_case_1_acceleration", pe1=30, sector_pe1=20),
        "BUSINESS: HVAC for data centers. Backlog rose to a record.",
    )
    assert len(calls) == 2
    assert result.supports_outlier is True
    assert "premium" in result.why.lower()
    assert "backlog" in [k.lower() for k in result.kpis]
    assert "generic_kpis_stripped" in result.red_flags


def test_qualitative_json_fail_both_passes_is_null(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)

    def boom(system: str, user: str, **kwargs):
        raise json.JSONDecodeError("Unterminated string", "{", 0)

    monkeypatch.setattr("ptm.llm.chat_json", boom)
    result = qualitative(Candidate(ticker="PFE", side=Side.SHORT), "BUSINESS: Pfizer sells medicines.")
    assert result.supports_outlier is None
    assert "llm_json_failed" in result.red_flags


def test_qualitative_verdict_json_fail_returns_bool(monkeypatch):
    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)

    def fake_chat(system: str, user: str, **kwargs):
        if "Extract operating facts" in system:
            return {"business_in_one_line": "Pays claims", "operating_plan": "Cut costs", "kpis": ["loss ratio"], "red_flags": []}
        raise json.JSONDecodeError("Unterminated string", "{", 0)

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    result = qualitative(Candidate(ticker="PFE", side=Side.SHORT, eg_case="short_non_ideal"), "BUSINESS: insurer")
    assert result.supports_outlier is False
    assert "llm_json_failed_verdict" in result.red_flags


def test_trailing_commas_are_repaired():
    """The most common small-model syntax error must not cost an idea its
    catalysts; observed at ~2% of calls across a 308-name run."""
    from ptm.llm import _extract_json

    got = _extract_json('{"non_earnings": ["a", "b",], "meaningful": true,}')
    assert got["non_earnings"] == ["a", "b"]
    assert got["meaningful"] is True

    fenced = '```json\n{"a": [1, 2,],}\n```'
    assert _extract_json(fenced)["a"] == [1, 2]

    prefixed = 'Here you go: {"x": {"y": [1,],},} trailing text'
    assert _extract_json(prefixed)["x"]["y"] == [1]


def test_throttled_calls_are_retried_not_dropped(monkeypatch):
    """Running ideas concurrently made 429s routine. An idea silently losing its
    catalysts to a transient throttle reads exactly like 'no catalysts found'."""
    import ptm.llm as llm

    calls = {"n": 0}

    class Boom(Exception):
        status_code = 429

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Boom("Error code: 429 - Too Many Requests")

        class R:
            choices = [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]

        return R()

    monkeypatch.setattr(llm, "client", lambda: type("C", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(flaky)})()})()})())
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setattr(llm, "llm_available", lambda: True)

    out = llm.chat_json("sys", "user")
    assert out == {"ok": True}
    assert calls["n"] == 3, "should have retried through the throttle"


def test_throttle_detection():
    from ptm.llm import _is_throttled

    assert _is_throttled(Exception("Error code: 429 - Too Many Requests"))
    assert _is_throttled(Exception("rate limit exceeded"))
    assert _is_throttled(Exception("503 Service Unavailable"))
    assert not _is_throttled(Exception("400 Bad Request: malformed"))
    assert not _is_throttled(Exception("invalid api key"))


def test_llm_calls_are_paced(monkeypatch):
    """Pacing is the plan; retrying is the backstop."""
    import ptm.llm as llm
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "llm": {**base["llm"], "max_rps": 4.0}}
    monkeypatch.setattr(llm, "toml_settings", lambda: patched)

    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    ticks = iter([0.0, 0.0, 0.0, 0.05, 0.05, 0.05])
    monkeypatch.setattr(llm.time, "monotonic", lambda: next(ticks))

    llm._LLM_LAST_CALL[0] = 0.0
    llm._pace_llm()   # first call sets the clock
    llm._pace_llm()   # second is only 0.05s later, min gap is 0.25s
    assert slept and slept[0] > 0.1, f"should have waited for the gap, slept={slept}"


def test_pacing_disabled_when_rate_is_zero(monkeypatch):
    import ptm.llm as llm
    from ptm.config import toml_settings

    base = toml_settings()
    patched = {**base, "llm": {**base["llm"], "max_rps": 0}}
    monkeypatch.setattr(llm, "toml_settings", lambda: patched)
    slept = []
    monkeypatch.setattr(llm.time, "sleep", lambda s: slept.append(s))
    for _ in range(5):
        llm._pace_llm()
    assert slept == []


def test_verdict_uses_its_own_model():
    """The verdict is the only real gate on the book, so it may run on a larger
    model than extraction and templating."""
    import inspect

    from ptm import llm
    from ptm.config import toml_settings

    configured = toml_settings()["llm"].get("verdict_model")
    assert llm.verdict_model() == (configured or llm.model_name())

    source = inspect.getsource(llm.qualitative)
    assert "model=wanted_model" in source, "the verdict call must pin the model"
    assert "verdict_model_downgraded" in source, "a silent downgrade must be flagged"
    # Extraction must NOT: it is per-name and cheap work.
    extract_call = source.split("verdict_system")[0]
    assert "model=" not in extract_call


def test_pinned_model_is_tried_first(monkeypatch):
    import ptm.llm as llm

    seen = []

    def create(**kwargs):
        seen.append(kwargs["model"])

        class R:
            choices = [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]

        return R()

    monkeypatch.setattr(llm, "client", lambda: type("C", (), {"chat": type("Ch", (), {"completions": type("Co", (), {"create": staticmethod(create)})()})()})())
    llm.chat_json("s", "u", model="big/model")
    assert seen[0] == "big/model"


def test_silent_model_downgrade_is_flagged(monkeypatch):
    """A pinned verdict model that quietly falls back to a smaller one defeats
    the point of pinning it. Nine of twelve verdicts did exactly that."""
    from ptm.llm import qualitative
    from ptm.models import Candidate, Side

    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    monkeypatch.setattr("ptm.llm.verdict_model", lambda: "big/model")

    def fake_chat(system, user, *, model=None, used_out=None, **kwargs):
        if used_out is not None:
            used_out.append("small/model")   # the pinned model was not used
        if "Extract operating facts" in system:
            return {"business_in_one_line": "b", "operating_plan": "p",
                    "kpis": ["backlog"], "red_flags": [], "quotes": []}
        return {"supports_outlier": True, "why": "ok",
                "evidence_for": ["x"], "evidence_against": []}

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    out = qualitative(Candidate(ticker="X", side=Side.LONG, pe1=30.0, sector_pe1=15.0), "pack text")
    assert any(f.startswith("verdict_model_downgraded_to_") for f in out.red_flags), out.red_flags
    assert "small/model" in " ".join(out.red_flags), "the flag must name the model that answered"


def test_no_flag_when_the_pinned_model_answered(monkeypatch):
    from ptm.llm import qualitative
    from ptm.models import Candidate, Side

    monkeypatch.setattr("ptm.llm.llm_available", lambda: True)
    monkeypatch.setattr("ptm.llm.verdict_model", lambda: "big/model")

    def fake_chat(system, user, *, model=None, used_out=None, **kwargs):
        if used_out is not None:
            used_out.append("big/model")
        if "Extract operating facts" in system:
            return {"business_in_one_line": "b", "operating_plan": "p",
                    "kpis": ["backlog"], "red_flags": [], "quotes": []}
        return {"supports_outlier": True, "why": "ok",
                "evidence_for": ["x"], "evidence_against": []}

    monkeypatch.setattr("ptm.llm.chat_json", fake_chat)
    out = qualitative(Candidate(ticker="X", side=Side.LONG, pe1=30.0, sector_pe1=15.0), "pack text")
    assert not any("downgraded" in f for f in out.red_flags)


def test_absurd_magnitudes_are_dropped_but_the_claim_is_kept():
    """A $3.7bn capital plan came back as '+3700%'. Drop the number, keep the reason."""
    from ptm.llm import MAX_PLAUSIBLE_IMPACT_PCT, _evidence_items

    items = _evidence_items([
        {"claim": "Strong capital investment plan", "impact_pct": 3700.0,
         "impact_on": "revenue", "quantified": True},
        {"claim": "Revenue grew 9%", "impact_pct": 9.0, "impact_on": "revenue", "quantified": True},
    ])
    assert items[0].claim == "Strong capital investment plan"
    assert items[0].quantified is False and items[0].impact_pct is None
    assert items[1].quantified is True and items[1].impact_pct == 9.0
    assert MAX_PLAUSIBLE_IMPACT_PCT == 500.0


def test_sized_facts_put_changes_ahead_of_levels():
    """impact_pct is defined as a CHANGE, so "revenue grew 9%" can size a claim
    and "revenue was $87 million" cannot. The verdict sees a bounded list, so
    the order decides what survives the cut."""
    from ptm.llm import _sized_facts

    pack = (
        "ITEM 1 BUSINESS: We make things. "
        "MD&A: Revenue was $87 million for the quarter. "
        "Cash was $12 million at period end. "
        "8-K EX-99.1: Revenue grew 9% year over year. Margins expanded 200 bps."
    )
    facts = _sized_facts(pack)
    change_at = min(i for i, f in enumerate(facts) if "grew 9%" in f or "200 bps" in f)
    level_at = min(i for i, f in enumerate(facts) if "was $87 million" in f)
    assert change_at < level_at


def test_sized_facts_lead_with_the_reported_changes_block():
    """That block is computed from filings and consensus rather than parsed out
    of prose, so it is the most reliable thing in the pack."""
    from ptm.llm import _sized_facts

    pack = (
        "EDGAR FACTS: {}\n\n"
        "REPORTED CHANGES (computed from filings and consensus; use these to size claims):\n"
        "  - EPS change, consensus FY1 vs prior year: +46.5%\n"
        "  - Forward P/E 22.3 against a sector median of 12.3 (1.8x)\n\n"
        "MD&A: Revenue was $87 million.\n\n"
        "8-K EX-99.1: Revenue grew 9%."
    )
    facts = _sized_facts(pack)
    reported = [f for f in facts if f.startswith("[REPORTED]")]
    assert reported and reported[0].startswith("[REPORTED] EPS change, consensus FY1")
    assert not any("use these to size claims" in f for f in facts), "header text is not a figure"


def test_sized_facts_drop_duplicates_and_empty_packs():
    from ptm.llm import _sized_facts

    assert _sized_facts("") == []
    assert _sized_facts("No numbers here at all.") == []
    repeated = "Revenue grew 9%. " * 5
    assert len(_sized_facts(repeated)) == 1


def test_forward_looking_facts_outrank_reported_ones():
    """The category error this fixes: the verdict was comparing last quarter's
    realised growth to a forward consensus and calling the difference a
    mispricing. Analysts have seen that quarter too. Guidance and backlog are
    the only facts that bear on a print that has not happened yet."""
    from ptm.llm import _sized_facts

    pack = (
        "MD&A: Revenue grew 51.7% year over year in the quarter. "
        "Cash was $12 million at period end. "
        "8-K EX-99.1: Revenue for full year 2026 is now expected to be $1,560 to $1,600 million, "
        "representing growth of 38% to 41%."
    )
    facts = _sized_facts(pack)
    assert facts[0].startswith("[FORWARD]"), facts
    assert "full year 2026" in facts[0]
    assert any(f.startswith("[REPORTED]") and "51.7%" in f for f in facts)


def test_long_guidance_sentences_are_kept():
    """A 240-char cap was discarding the single best fact in the pack. Guidance
    sentences are long precisely because they carry several figures - SEZL's ran
    352 and 250 characters, so a raise to FY2026 guidance was filtered out while
    a standing balance figure survived."""
    from ptm.llm import _sized_facts

    guidance = (
        "8-K EX-99.1: This momentum supports our third raise to FY2026 guidance, taking "
        "Adjusted Net Income to $185 million and Adjusted Net Income per Diluted Share to $5.25, "
        "with Total Revenue Growth now at the high end of the prior range at 35% versus the "
        "30% we indicated last quarter, reflecting continued subscriber momentum."
    )
    assert len(guidance) > 240
    facts = _sized_facts(guidance)
    assert facts, "a long guidance sentence must not be dropped"
    assert facts[0].startswith("[FORWARD]")
    assert "FY2026 guidance" in facts[0]


def test_absurdly_long_text_is_still_rejected():
    """The cap was raised, not removed - a whole paragraph is not a fact."""
    from ptm.llm import _sized_facts, MAX_FACT_CHARS

    blob = "Revenue grew 9% and " * 60 + "margins expanded 200 bps."
    assert len(blob) > MAX_FACT_CHARS
    assert _sized_facts(blob) == []


def test_ranking_critical_fields_are_requested_first():
    """Measured on a live run: 5 of 15 verdict responses truncated mid-JSON, and
    filing_direction / momentum_durability appeared in only 8 and 7 of 15 - they
    were requested LAST, so truncation ate the two fields the ranking depends on
    while commentary survived."""
    import inspect

    from ptm import llm

    source = inspect.getsource(llm.qualitative)
    # The FIRST "Return JSON keys" belongs to the extract pass; the verdict block
    # is the one that mentions filing_direction.
    start = source.index("Return JSON keys", source.index("filing_direction (improving") - 400)
    keys = source[start:source.index("Side={candidate.side.value}")]
    for early in ("filing_direction", "momentum_durability"):
        assert early in keys, f"{early} must be requested"
    assert keys.index("filing_direction") < keys.index("supports_outlier")
    assert keys.index("momentum_durability") < keys.index("evidence_for")


def test_the_dead_mispricing_payload_is_no_longer_requested():
    """expected_surprise_pct and friends drove nothing after the move to
    revision momentum - they were pure response length, and the response was
    running out of room."""
    import inspect

    from ptm import llm

    source = inspect.getsource(llm.qualitative)
    start = source.index("Return JSON keys", source.index("filing_direction (improving") - 400)
    keys = source[start:source.index("Side={candidate.side.value}")]
    for dead in ("expected_surprise_pct", "surprise_basis", "gap_confidence", "gap_basis_type"):
        assert dead not in keys, f"{dead} is no longer used and must not be asked for"


def test_dead_mispricing_fields_are_not_in_the_schema():
    from ptm.models import QualResult

    dead = {
        "market_expectation",
        "deviation",
        "priced_in",
        "expected_surprise_pct",
        "surprise_basis",
        "gap_confidence",
        "gap_basis_type",
    }
    assert dead.isdisjoint(QualResult.model_fields)


def test_retry_keeps_both_ends_of_the_prompt():
    """The retry path kept only the first 4000 characters. The verdict question
    appends the expectations and theme blocks at the END, so a retry silently
    discarded exactly the context it was meant to help with."""
    from ptm.llm import _shorten_middle

    prompt = "KEYS-AT-THE-START " * 100 + "filler " * 500 + "THEMES-AT-THE-END"
    out = _shorten_middle(prompt, 1000)
    assert len(out) <= 1000
    assert out.startswith("KEYS-AT-THE-START")
    assert out.endswith("THEMES-AT-THE-END")
    assert _shorten_middle("short", 1000) == "short"
