"""Feature-layer tests. Expected values come from knowledge-base worked examples only."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from strategy_compiler.engine import features as F
from strategy_compiler.engine.data import Bar, MarketData, Series, View
from strategy_compiler.engine.errors import MissingParameter, UnsupportedCondition
from strategy_compiler.engine.freeze import FrozenConfig, InstrumentConfig
from strategy_compiler.engine.market_state import Ctx
from strategy_compiler.tests.synthetic import NY, long_sweep_displacement_scenario

BASE = dict(
    governing_swing_tier="short_term", displacement_range_multiple=2.0, displacement_lookback=3,
    displacement_body_ratio_min=0.6, sweep_min_penetration=0.0, sweep_reclaim_bars=3,
    equal_level_tolerance=0.0002, risk_fraction=0.01, stop_buffer_ticks=10,
    first_target_allocation=0.5, fib_anchor="wick", ote_levels=[0.62, 0.705, 0.79],
    entry_level="fvg_ce", entry_trigger="limit_at_zone", ltf_confirmation_signal="ltf_mss",
    asian_window_ET=["20:00", "00:00"], daily_bias_method="single_mss",
    daily_open_definition="new_york_midnight",
)
ROLES = {"htf": "1d", "htf_intermediate": "4h", "ltf_structure": "5m",
         "ltf_confirmation": "1m", "execution": "5m"}


def _ctx(md=None, params=None, cutoff=None):
    md = md or long_sweep_displacement_scenario()
    cfg = FrozenConfig("S01-BUY-11STEP", InstrumentConfig("SYNTH", 0.00001, 100000.0),
                       ROLES, params=dict(params or BASE), setup_expiry_bars=60)
    cutoff = cutoff or md.series["5m"].bars[-1].close_time
    return Ctx(View(md, cutoff), cfg, ROLES, {}, 100000.0)


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol


# --- values taken from knowledge-base worked examples ----------------------------------
def test_INT_M04_EX01_consequent_encroachment():
    ctx = _ctx()
    ce = F.f_midpoint(ctx, {"low": 1.2540, "high": 1.2565})
    assert approx(ce, 1.25525)                       # KB states 'approximately 1.2552'


def test_BEG_M11_EX01_entry_is_the_gap_midpoint():
    ctx = _ctx()
    assert approx(F.f_midpoint(ctx, {"low": 1.08095, "high": 1.08142}), 1.081185)


def test_BEG_M07_C03_fibonacci_levels_100_to_200():
    ctx = _ctx()
    f = F.f_fib_levels(ctx, origin=100.0, termination=200.0)
    assert approx(f["eq"], 150) and approx(f["ote_start"], 138)
    assert approx(f["ote_sweet"], 129.5) and approx(f["ote_end"], 121)
    assert approx(f["ext_27"], 227) and approx(f["ext_62"], 262)
    assert F.f_in_ote(ctx, f, price=130) and not F.f_in_ote(ctx, f, price=140)
    assert F.f_retracement_class(ctx, f, 150) == "shallow"
    assert F.f_retracement_class(ctx, f, 129) == "standard"
    assert F.f_retracement_class(ctx, f, 115) == "deep"


def test_INT_M07_R02_alternative_ote_constants():
    p = dict(BASE, ote_levels=[0.618, None, 0.786], fib_anchor="body")
    f = F.f_fib_levels(_ctx(params=p), origin=100.0, termination=200.0)
    assert approx(f["ote_start"], 138.2) and f["ote_sweet"] is None and approx(f["ote_end"], 121.4)


def test_BEG_M12_EX01_risk_and_r_multiple():
    ctx = _ctx()
    entry, stop, t1 = 2649.90, 2656.40, 2644.20
    assert approx(stop - entry, 6.50)
    assert approx(F.f_r_multiple(ctx, entry, stop, t1), 5.70 / 6.50)


def test_INT_M12_EX01_position_size_is_one_percent_at_55_pips():
    ctx = _ctx()
    ctx.equity = 100_000.0
    cfg = ctx.cfg
    cfg.instrument = InstrumentConfig("EURUSD", 0.00001, 1.0)
    size = F.f_position_size(ctx, 1.0865, 1.0810)
    assert approx(size * 0.0055, 1000.0, 1e-6)


# --- structures found in the synthetic scenario -----------------------------------------
def test_scenario_prints_the_documented_sequence():
    md = long_sweep_displacement_scenario()
    bars5 = md.series["ltf" if False else "5m"].bars
    raid_i = next(i for i, b in enumerate(bars5) if approx(b.low, 1.07880, 1e-9))
    # decide at the close of candle 3 of the gap, exactly as the specification's step 6 does
    ctx = _ctx(md=md, cutoff=bars5[raid_i + 3].close_time)
    sweep = F.f_sweep(ctx, "ltf_structure", level=1.0806, side="ssl", since_index=raid_i - 1)
    assert sweep["classification"] == "raid"
    assert approx(sweep["extreme"], 1.07880)
    assert sweep["sweep_index"] == raid_i

    assert F.f_displacement(ctx, "ltf_structure", at_index=raid_i + 2, direction="bullish")
    assert F.f_mss(ctx, "ltf_structure", at_index=raid_i + 2, direction="bullish")
    gap = F.f_fvg(ctx, "ltf_structure", direction="bullish", since_index=raid_i)
    assert approx(gap["low"], 1.08200) and approx(gap["high"], 1.08600)
    assert approx(gap["ce"], 1.08400)
    assert F.f_structure_state(ctx, "htf") == "bullish"


def test_wick_only_breach_is_not_a_market_structure_shift():
    """BEG-M03-R01: a wick through the governing point never qualifies."""
    ctx = _ctx()
    bars = ctx.bars("ltf_structure")
    raid_i = next(i for i, b in enumerate(bars) if approx(b.low, 1.07880, 1e-9))
    # the raid candle pierces the swing low with its wick and closes back inside
    assert not F.f_mss(ctx, "ltf_structure", at_index=raid_i, direction="bearish")


# --- refusal to guess ---------------------------------------------------------------------
def test_unfrozen_parameter_raises_rather_than_defaulting():
    p = dict(BASE)
    p.pop("displacement_body_ratio_min")
    ctx = _ctx(params=p)
    try:
        F.f_displacement(ctx, "ltf_structure", at_index=-1, direction="bullish")
        assert False, "expected UnspecifiedParameter"
    except Exception as e:
        assert type(e).__name__ == "UnspecifiedParameter"


def test_off_menu_choice_is_rejected():
    p = dict(BASE, fib_anchor="close_to_close")
    ctx = _ctx(params=p)
    try:
        F.f_displacement_leg(ctx, "ltf_structure", at_index=-1, direction="bullish")
        assert False, "expected MissingParameter"
    except MissingParameter:
        pass


def test_reclaim_refuses_to_run_without_a_recorded_operationalisation():
    p = dict(BASE, reclaim_definition="close_back_beyond_level")
    ctx = _ctx(params=p)
    try:
        F.f_level_reclaimed(ctx, "ltf_structure", level=1.0806, side="ssl", from_index=0,
                            within_bars=3)
        assert False, "expected UnsupportedCondition"
    except UnsupportedCondition:
        pass
    ctx.cfg.operationalisations["U-RECLAIM"] = "close back beyond the swept level"
    assert F.f_level_reclaimed(ctx, "ltf_structure", level=1.0806, side="ssl", from_index=0,
                               within_bars=3) in (True, False)


def test_inversion_refuses_to_run_without_a_recorded_operationalisation():
    p = dict(BASE, decisive_close_definition="body_close_beyond",
             inversion_hold_definition="retest_then_close_beyond_zone_without_decisive_break")
    ctx = _ctx(params=p)
    try:
        F.f_fvg_inverted(ctx, "ltf_structure", {"direction": "bearish", "low": 1.0, "high": 1.1,
                                                "ce": 1.05, "index": 0})
        assert False, "expected UnsupportedCondition"
    except UnsupportedCondition:
        pass
