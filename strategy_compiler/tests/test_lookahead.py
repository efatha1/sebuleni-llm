"""Look-ahead control (ADV-M18-R04).

The property under test: a label computed at bar t must not change when bars after t are added to
the dataset. Every feature is therefore evaluated twice — once against a dataset truncated at t,
once against the full dataset with the view cut at t — and the two must agree exactly.
"""
from __future__ import annotations

from strategy_compiler.engine import features as F
from strategy_compiler.engine.data import MarketData, Series, View
from strategy_compiler.engine.freeze import FrozenConfig, InstrumentConfig
from strategy_compiler.engine.market_state import Ctx
from strategy_compiler.tests.synthetic import long_sweep_displacement_scenario
from strategy_compiler.tests.test_features import BASE, ROLES


def _truncate(md: MarketData, cutoff) -> MarketData:
    return MarketData(
        instrument=md.instrument,
        series={tf: Series(tf, [b for b in s.bars if b.close_time <= cutoff])
                for tf, s in md.series.items()},
    )


def _ctx(md, cutoff):
    cfg = FrozenConfig("S01-BUY-11STEP", InstrumentConfig("SYNTH", 0.00001, 100000.0),
                       ROLES, params=dict(BASE), setup_expiry_bars=60)
    return Ctx(View(md, cutoff), cfg, ROLES, {}, 100000.0)


PROBES = [
    ("structure_state", lambda c: F.f_structure_state(c, "ltf_structure")),
    ("governing_point", lambda c: F.f_governing_point(c, "ltf_structure")),
    ("swing_lows", lambda c: [round(s["price"], 6) for s in
                              F.f_swing_points(c, "ltf_structure", "low")]),
    ("swing_highs", lambda c: [round(s["price"], 6) for s in
                               F.f_swing_points(c, "ltf_structure", "high")]),
    ("dealing_range", lambda c: F.f_dealing_range(c, "htf")),
    ("pd_location", lambda c: F.f_pd_location(c, "htf", price_tf="ltf_structure")),
    ("latest_bullish_fvg", lambda c: F.f_fvg(c, "ltf_structure", "bullish", 0)),
    ("displacement_now", lambda c: F.f_displacement(c, "ltf_structure", -1, "bullish")),
    ("mss_now", lambda c: F.f_mss(c, "ltf_structure", -1, "bullish")),
    ("asian_range", lambda c: F.f_session_range(c, "ltf_structure", "asian_window_ET")),
    ("daily_open", lambda c: F.f_period_open(c, "daily", "ltf_structure")),
    ("sell_pools", lambda c: [round(p["price"], 6) for p in
                              F.f_liquidity_pools(c, "ltf_structure", "sell",
                                                  ["swing", "equal", "prev_day"], select="all")]),
]


def test_no_feature_depends_on_future_bars():
    md = long_sweep_displacement_scenario()
    bars = md.series["5m"].bars
    checked = 0
    for i in range(120, len(bars), 2):
        cutoff = bars[i].close_time
        full = _ctx(md, cutoff)
        trunc = _ctx(_truncate(md, cutoff), cutoff)
        for name, probe in PROBES:
            a, b = probe(full), probe(trunc)
            assert a == b, f"bar {i}: '{name}' changed when future bars were present: {a} != {b}"
            checked += 1
    assert checked > 500, checked


def test_session_range_is_hidden_until_the_window_closes():
    """An in-progress window must not be readable (P-TIME-02 look-ahead control)."""
    md = long_sweep_displacement_scenario()
    bars = md.series["5m"].bars
    from strategy_compiler.engine.market_state import in_session, session_range

    saw_open_window = False
    for i in range(20, len(bars)):
        ctx = _ctx(md, bars[i].close_time)
        if in_session(ctx, "asian_window_ET"):
            saw_open_window = True
            blocks = session_range(ctx, "ltf_structure", "asian_window_ET")
            if blocks is not None:
                # only a PREVIOUS, completed window may be visible
                assert blocks["end_index"] < i
    assert saw_open_window


def test_swing_points_are_published_one_candle_late():
    md = long_sweep_displacement_scenario()
    bars = md.series["5m"].bars
    for i in range(60, len(bars), 11):
        ctx = _ctx(md, bars[i].close_time)
        for s in F.f_swing_points(ctx, "ltf_structure", "low"):
            assert s["confirmed_at_index"] <= i
            assert s["confirmed_at_index"] == s["index"] + 1
