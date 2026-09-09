"""Enriched trade recording: excursions, market-state snapshot and the concept audit.

The enrichment is diagnostic only. The last test in this module is the one that matters most: it
asserts the recording did not disturb the determinism contract.
"""
from __future__ import annotations

from strategy_compiler.engine import backtest as BT
from strategy_compiler.engine import dsl as DSL
from strategy_compiler.engine.freeze import FrozenConfig
from strategy_compiler.tests import paths
from strategy_compiler.tests.synthetic import long_sweep_displacement_scenario

RECORD_KEYS = {
    "trade_id", "strategy_id", "instrument", "direction", "entry_time", "entry_price",
    "stop_price", "size", "htf_state", "ltf_state", "session_state", "entry_session",
    "liquidity_state", "used_concepts", "available_unused", "result", "setup_events",
    "targets", "bindings",
}


def _run():
    return BT.run(DSL.load(f"{paths.COMPILED}/S01-BUY-11STEP.json"),
                  long_sweep_displacement_scenario(),
                  FrozenConfig.from_file(paths.CONFIG_S01))


def test_a_scenario_produces_a_trade():
    res = _run()
    assert len(res.trades) >= 1, res.diagnostics


def test_b_max_favourable_excursion_is_positive():
    t = _run().trades[0]
    assert t.mfe > 0, t.mfe


def test_c_max_adverse_excursion_is_negative():
    t = _run().trades[0]
    assert t.mae < 0, t.mae


def test_d_duration_is_recorded():
    t = _run().trades[0]
    assert t.duration_bars > 0
    # management ran at least as far as the bar that printed the first exit
    assert t.duration_bars >= t.exits[0].bar_index - t.entry_index


def test_e_higher_timeframe_structure_is_captured():
    t = _run().trades[0]
    assert t.htf_state["structure"] == "bullish"
    assert t.htf_state["dealing_range_equilibrium"] is not None


def test_f_entry_session_is_recorded():
    t = _run().trades[0]
    assert isinstance(t.entry_session, str) and t.entry_session


def test_g_used_concepts_cover_the_latched_setup():
    t = _run().trades[0]
    assert len(t.used_concepts) >= 4
    assert all(t.used_concepts.values())
    # the audit must line up exactly with the events the setup machine latched
    assert set(t.used_concepts) == {e["node_id"] for e in t.setup_events}


def test_h_available_unused_is_populated():
    t = _run().trades[0]
    assert len(t.available_unused) >= 8


def test_i_ote_is_audited():
    t = _run().trades[0]
    assert "ote_existed" in t.available_unused


def test_j_order_block_is_audited():
    t = _run().trades[0]
    assert "order_block_existed" in t.available_unused


def test_k_records_expose_every_required_key():
    res = _run()
    records = res.as_records()
    assert len(records) == len(res.trades)
    for i, rec in enumerate(records):
        assert set(rec) == RECORD_KEYS, sorted(set(rec) ^ RECORD_KEYS)
        assert rec["trade_id"] == f"{res.strategy_id}_{i:06d}"
        assert set(rec["result"]) == {"r_total", "mfe", "mae", "duration_bars",
                                      "exit_reason", "exits"}
        for e in rec["result"]["exits"]:
            assert set(e) == {"reason", "price", "allocation", "r_multiple"}
        for e in rec["setup_events"]:
            assert set(e) == {"node_id", "bar_index", "time"}


def test_l_enrichment_does_not_break_determinism():
    a, b = _run(), _run()
    assert a.manifest["trades_digest"] == b.manifest["trades_digest"]
    assert a.as_records() == b.as_records()


def test_m_diagnostics_are_excluded_from_the_digest():
    """Mutating only diagnostic fields must leave trades_digest untouched."""
    res = _run()
    before = BT.digest([BT._digest_payload(t) for t in res.trades])
    for t in res.trades:
        t.mfe, t.mae, t.duration_bars = 99.0, -99.0, 9999
        t.entry_session = "mutated"
        t.htf_state = {"mutated": True}
        t.available_unused = {"mutated": True}
        t.used_concepts = {"mutated": True}
    after = BT.digest([BT._digest_payload(t) for t in res.trades])
    assert before == after == res.manifest["trades_digest"]
