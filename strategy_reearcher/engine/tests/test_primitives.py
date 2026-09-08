"""
test_primitives.py — every expected value below is taken verbatim from a knowledge-base example
(the KB object id is in each test name/comment). Run:  python3 test_primitives.py
Also runnable under pytest.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

import ict_primitives as P

# Frozen research parameters used ONLY where the KB is unspecified. These values are arbitrary
# test choices so that the KB examples can be replayed; they are NOT knowledge-base doctrine.
FP = P.FrozenParams(
    displacement_range_multiple=2.0, displacement_lookback=3, displacement_body_ratio_min=0.6,
    equal_level_tolerance=0.5, sweep_min_penetration=0.0, sweep_reclaim_bars=3,
    fib_anchor="body", ote_levels=(0.62, 0.705, 0.79),
    london_open_kz=(time(2, 0), time(5, 0)), new_york_open_kz=(time(7, 0), time(10, 0)),
    asian_window=(time(20, 0), time(0, 0)), london_close_kz=(time(10, 0), time(12, 0)),
    risk_fraction=0.01,
)


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def turning_points(seq):
    """Treat a KB price sequence as alternating turning points: highs are local maxima incl. endpoints
    where the KB counts them (e.g. 100 as the first low in BEG-M03-C01)."""
    highs = [seq[i] for i in range(len(seq)) if (i == 0 or seq[i] > seq[i - 1]) and (i == len(seq) - 1 or seq[i] > seq[i + 1])]
    lows = [seq[i] for i in range(len(seq)) if (i == 0 or seq[i] < seq[i - 1]) and (i == len(seq) - 1 or seq[i] < seq[i + 1])]
    return highs, lows


# ---------------- P-SWING-01 ----------------
def test_BEG_M01_C01_swing_high():
    seq = [100, 105, 102, 108, 104]
    idx = P.swing_highs(seq)
    assert [seq[i] for i in idx] == [105, 108]


def test_BEG_M01_C02_swing_low():
    seq = [110, 104, 108, 101, 106]
    idx = P.swing_lows(seq)
    assert [seq[i] for i in idx] == [104, 101]


# ---------------- P-SWING-02 ----------------
def test_INT_M01_R01_intermediate_term_high():
    # an STH flanked by lower STHs on both sides
    sth = [105, 108, 112, 109, 107]
    assert [sth[i] for i in P.intermediate_term_highs(sth)] == [112]


# ---------------- P-STRUCT-01 ----------------
def test_BEG_M03_C01_bullish_structure():
    highs, lows = turning_points([100, 108, 104, 115, 109, 122])
    assert highs == [108, 115, 122] and lows == [100, 104, 109]
    assert P.structure_state(highs, lows) == "bullish"
    assert P.governing_point("bullish", highs, lows) == 109          # BEG-M03-C02


def test_BEG_M03_C04_bearish_structure():
    highs, lows = turning_points([122, 112, 118, 105, 111, 98])
    assert P.structure_state(highs, lows) == "bearish"
    assert P.governing_point("bearish", highs, lows) == 111


def test_BEG_M01_C05_single_lower_high_is_not_bearish_structure():
    highs, lows = turning_points([112, 106, 109, 101, 104])
    # KB: 'a caution flag but not yet confirmation' -> one LH + one LL only
    assert P.structure_state(highs, lows) == "range"


# ---------------- P-MSS-01 ----------------
def test_BEG_M03_C05_bearish_mss():
    # governing low 109; sharp close to 101 with displacement -> MSS
    c = P.Candle(open=120, high=121, low=101, close=101)
    assert P.mss_strict(c, governing_level=109, prior_state="bullish", displacement_ok=True)
    assert not P.mss_strict(c, 109, "bullish", displacement_ok=False)          # BEG-M03-R02
    wick = P.Candle(open=115, high=116, low=105, close=112)
    assert not P.mss_strict(wick, 109, "bullish", displacement_ok=True)         # BEG-M03-R01 wick insufficient


# ---------------- P-FVG-01 ----------------
def test_BEG_M05_C04_bullish_fvg_and_ce():
    c1 = P.Candle(open=106, high=107, low=105, close=106.5)
    c2 = P.Candle(open=107, high=117.5, low=107, close=117)
    c3 = P.Candle(open=117, high=119, low=116, close=118)
    g = P.fvg(c1, c2, c3)
    assert g and g.direction == "bullish" and g.low == 107 and g.high == 116
    assert approx(g.ce, 111.5)


def test_INT_M04_EX01_ce():
    g = P.FVG("bullish", 1.2540, 1.2565, 2)
    assert approx(g.ce, 1.25525, 1e-9)        # KB states 'approximately 1.2552'


def test_BEG_M11_EX01_ce_equals_entry():
    g = P.FVG("bullish", 1.08095, 1.08142, 2)
    assert approx(g.ce, 1.08118, 6e-6)   # true midpoint 1.081185; KB prints 1.08118 (rounded to 5 dp)


def test_INT_M04_R01_touching_wicks_no_fvg():
    c1 = P.Candle(100, 107, 105, 106)
    c2 = P.Candle(107, 117, 107, 117)
    c3 = P.Candle(117, 119, 107, 118)        # c3 low touches c1 high -> no FVG
    assert P.fvg(c1, c2, c3) is None


def test_P_FVG_02_failure_requires_body_close():
    g = P.FVG("bullish", 107, 116, 2)
    wick_through = [P.Candle(118, 119, 106, 117)]       # wick below 107 but close inside -> partially mitigated
    assert P.fvg_state(g, wick_through) == "partially_mitigated"
    body_through = [P.Candle(112, 113, 104, 105)]
    assert P.fvg_state(g, body_through) == "failed"


# ---------------- P-DISP-01 ----------------
def test_BEG_M05_C01_displacement_candle():
    cs = [P.Candle(108, 108.5, 107, 107.2), P.Candle(107.2, 107.5, 106, 106.3), P.Candle(106.3, 106.8, 105.8, 106),
          P.Candle(106, 118.2, 106, 118)]  # 106 -> 118 one large forceful candle
    assert P.is_displacement(cs, 3, FP, broke_level=108.5)
    small = cs[:3] + [P.Candle(106, 107, 105.5, 106.8)]
    assert not P.is_displacement(small, 3, FP)


def test_displacement_requires_frozen_params():
    cs = [P.Candle(1, 2, 0, 1)] * 5
    try:
        P.is_displacement(cs, 4, P.FrozenParams())
        assert False, "should raise"
    except P.UnspecifiedParameter:
        pass


# ---------------- P-OB-01 / P-OB-02 ----------------
def test_BEG_M06_C01_order_block():
    cs = [P.Candle(111, 112.5, 110.5, 112), P.Candle(112, 112, 110, 110), P.Candle(110, 122, 110, 122), P.Candle(122, 124, 121, 124)]
    ob = P.order_block(cs, 2)
    assert ob and ob.direction == "bullish" and ob.low == 110 and ob.high == 112


def test_BEG_M06_C02_and_C03_mitigation_vs_breaker():
    ob = P.OrderBlock("bullish", 108, 110, 0)
    # BEG-M06-C02 style: retest into the zone, no body close below -> mitigation
    assert P.breaker_or_mitigation(ob, [P.Candle(118, 118, 111.5, 112), P.Candle(112, 121, 109.5, 121)]) == "mitigation"
    # BEG-M06-C03: closes decisively below 108 -> breaker
    assert P.breaker_or_mitigation(ob, [P.Candle(120, 120, 106, 106.5)]) == "breaker"


def test_BEG_M06_C04_fvg_ob_confluence_overlap():
    assert P.zones_overlap(107, 116, 106, 108) == (107, 108)


# ---------------- P-LIQ-01 / P-LIQ-02 ----------------
def test_BEG_M04_C05_equal_highs():
    highs, _ = turning_points([100, 115, 108, 114, 103, 115.2])
    groups = P.equal_levels(highs, FP)
    assert groups == [[115, 115.2]]


def test_BEG_M04_C08_liquidity_sweep_raid():
    # SSL at 100: 103 -> 100 -> 98 -> 104
    cs = [P.Candle(103, 103.5, 102.5, 103), P.Candle(103, 103, 100, 100.2), P.Candle(100.2, 100.5, 98, 99), P.Candle(99, 104, 99, 104)]
    s = P.detect_sweep(cs, level=100, side="ssl", start=0, params=FP)
    assert s and s.classification == "raid" and s.extreme == 98 and s.reversal_index == 3


def test_INT_M02_R05_continuation_not_raid():
    cs = [P.Candle(103, 103, 100, 100.2), P.Candle(100.2, 100.5, 98, 98.5), P.Candle(98.5, 98.7, 97, 97.2),
          P.Candle(97.2, 97.5, 96, 96.3), P.Candle(96.3, 96.4, 95, 95.2)]
    s = P.detect_sweep(cs, 100, "ssl", 0, FP)
    assert s and s.classification == "continuation"


# ---------------- P-RANGE-01 ----------------
def test_INT_M06_EX01_dealing_range():
    r = P.DealingRange(high=1.1000, low=1.0800)
    assert approx(r.equilibrium, 1.0900)
    assert r.location(1.0860) == "discount"
    assert r.location(1.0960) == "premium"


def test_BEG_M07_C02_equilibrium_100_200():
    r = P.DealingRange(200, 100)
    assert r.equilibrium == 150 and r.location(130) == "discount"


# ---------------- P-FIB-01 ----------------
def test_BEG_M07_C03_fib_levels_100_200():
    f = P.fib_levels(origin=100, termination=200, params=FP)
    assert approx(f.eq, 150) and approx(f.ote_start, 138) and approx(f.ote_sweet, 129.5) and approx(f.ote_end, 121)
    assert approx(f.ext_27, 227) and approx(f.ext_62, 262)


def test_BEG_M07_C04_C05_retracement_into_ote():
    f = P.fib_levels(100, 200, FP)
    assert f.in_ote(130) and f.in_ote(129)
    assert not f.in_ote(140) and not f.in_ote(160)
    assert f.retracement_class(150) == "shallow" and f.retracement_class(129) == "standard" and f.retracement_class(115) == "deep"


def test_BEG_M07_C06_ob_inside_ote():
    f = P.fib_levels(100, 200, FP)
    lo, hi = sorted((f.ote_end, f.ote_start))
    assert P.zones_overlap(lo, hi, 125, 128) == (125, 128)


def test_INT_M07_R02_alternative_levels():
    alt = P.FrozenParams(fib_anchor="wick", ote_levels=(0.618, None, 0.786))
    f = P.fib_levels(100, 200, alt)
    assert approx(f.ote_start, 138.2) and f.ote_sweet is None and approx(f.ote_end, 121.4)


# ---------------- P-TIME-01 ----------------
def test_BEG_M08_C01_kill_zone_membership():
    t_in = datetime(2024, 3, 5, 3, 0, tzinfo=ZoneInfo("America/New_York"))
    t_out = datetime(2024, 3, 5, 18, 0, tzinfo=ZoneInfo("America/New_York"))
    assert P.in_window(t_in, FP.london_open_kz) and not P.in_window(t_out, FP.london_open_kz)
    # Asian window wraps midnight
    assert P.in_window(datetime(2024, 3, 5, 22, 0, tzinfo=ZoneInfo("America/New_York")), FP.asian_window)


def test_BEG_M08_R05_dst_anchoring_london_time_converts():
    # 08:00 London (BST) on 2024-04-02 == 03:00 New York (EDT) -> inside LOKZ
    t = datetime(2024, 4, 2, 8, 0, tzinfo=ZoneInfo("Europe/London"))
    assert P.in_window(t, FP.london_open_kz)


# ---------------- P-RISK-01 ----------------
def test_INT_M12_EX01_position_size_55_pips_equals_1pct():
    # entry 1.0865, stop 1.0810 -> 55 pips; size so that 55 pips = 1% of equity
    size = P.position_size(equity=100_000, entry=1.0865, stop=1.0810, value_per_unit_move=1.0, params=FP)
    assert approx(size * 0.0055, 1000.0, 1e-6)


def test_BEG_M12_EX01_risk_and_r_multiple():
    entry, stop, t1 = 2649.90, 2656.40, 2644.20
    assert approx(stop - entry, 6.50, 1e-9)                 # 'Risk approximately 6.50 points'
    assert approx(entry - t1, 5.70, 1e-9)                   # 'nearer target offers ~5.70 points'
    assert approx(P.r_multiple(entry, stop, t1), 5.70 / 6.50, 1e-9)


if __name__ == "__main__":
    import sys
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {name}: {e}")
        except Exception as e:  # noqa
            failed += 1
            print(f"ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
