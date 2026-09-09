"""Feature implementations — the closed set the compiled DSL may call.

Every function maps 1:1 onto an entry in requirements/feature_registry.json and, through it, onto
a primitive in strategy_reearcher/catalog/primitives.json. Wherever the reference implementation
`ict_primitives` already covers an operation it is delegated to rather than re-derived, so the
trading logic has exactly one definition.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from ._kb import P
from .data import tf_rank
from .errors import MissingData, MissingParameter, UnsupportedCondition
from .market_state import (
    Ctx,
    dealing_range as _dealing_range,
    fvg_registry,
    in_session as _in_session,
    order_block_at,
    pd_location as _pd_location,
    period_open as _period_open,
    pool_registry,
    previous_period_extreme,
    range_depth_fraction as _range_depth_fraction,
    session_range as _session_range,
    structure,
    swing_registry,
    _tier,
)

REGISTRY: Dict[str, Callable[..., Any]] = {}


def feature(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        return fn

    return deco


def _idx(ctx: Ctx, tf: str, at_index) -> Optional[int]:
    """None propagates: a bar reference built from a binding that has not been published yet is
    'no value', not index zero."""
    if at_index is None:
        return None
    n = len(ctx.bars(tf))
    return n + at_index if at_index < 0 else at_index


# ---------------------------------------------------------------------------
# data access (not trading concepts)
# ---------------------------------------------------------------------------
@feature("bar")
def f_bar(ctx: Ctx, tf: str, component: str = "close", at_index: int = -1):
    """`component` is deliberately not called `field`: `field` is the DSL's generic accessor for
    picking a key out of a feature's returned mapping, and the two must not collide."""
    bars = ctx.bars(tf)
    if not bars:
        return None
    i = _idx(ctx, tf, at_index)
    if i is None or not 0 <= i < len(bars):
        return None
    if component == "index":
        return i
    return getattr(bars[i], component)


@feature("latest_index")
def f_latest_index(ctx: Ctx, tf: str):
    return len(ctx.bars(tf)) - 1


# ---------------------------------------------------------------------------
# P-SWING-01 / P-SWING-02
# ---------------------------------------------------------------------------
@feature("swing_points")
def f_swing_points(ctx: Ctx, tf: str, side: str, tier: Optional[str] = None):
    return swing_registry(ctx, tf, side, tier or _tier(ctx))


@feature("swing_points_intermediate")
def f_swing_points_intermediate(ctx: Ctx, tf: str, side: str):
    return swing_registry(ctx, tf, side, "intermediate")


# ---------------------------------------------------------------------------
# P-STRUCT-01
# ---------------------------------------------------------------------------
@feature("structure_state")
def f_structure_state(ctx: Ctx, tf: str, upto_index: Optional[int] = None):
    return structure(ctx, tf, upto_index)["state"]


@feature("governing_point")
def f_governing_point(ctx: Ctx, tf: str, upto_index: Optional[int] = None):
    return structure(ctx, tf, upto_index)["governing_point"]


# ---------------------------------------------------------------------------
# P-DISP-01
# ---------------------------------------------------------------------------
@feature("displacement")
def f_displacement(ctx: Ctx, tf: str, at_index: int = -1, direction: Optional[str] = None,
                   broke_level: Optional[float] = None):
    cs = ctx.candles(tf)
    i = _idx(ctx, tf, at_index)
    if i is None or not 0 <= i < len(cs):
        return False
    if direction == "bullish" and not cs[i].bullish:
        return False
    if direction == "bearish" and not cs[i].bearish:
        return False
    return P.is_displacement(cs, i, ctx.fp(), broke_level=broke_level)


@feature("displacement_leg")
def f_displacement_leg(ctx: Ctx, tf: str, at_index: int = -1, direction: str = "bullish"):
    """Origin/termination of the impulse leg containing the displacement candle.

    Origin is the leg's opposing extreme; termination is the extreme reached in the direction of
    travel up to the decision bar (S01 Step 8: 'from the swept low to the pre-retracement high').
    Body-vs-wick price selection follows the frozen fib_anchor (BEG-M07-R01 vs INT-M07-R01).
    """
    anchor = ctx.cfg.require_choice("fib_anchor", ["body", "wick"])
    bars = ctx.bars(tf)
    i = _idx(ctx, tf, at_index)
    if i is None or not 0 <= i < len(bars):
        return None
    same = (lambda b: b.close > b.open) if direction == "bullish" else (lambda b: b.close < b.open)
    if not same(bars[i]):
        return None
    s = i
    while s - 1 >= 0 and same(bars[s - 1]):
        s -= 1

    def lo(b):
        return min(b.open, b.close) if anchor == "body" else b.low

    def hi(b):
        return max(b.open, b.close) if anchor == "body" else b.high

    run = bars[s : i + 1]
    forward = bars[s:]
    if direction == "bullish":
        origin = min(lo(b) for b in run)
        termination = max(hi(b) for b in forward)
    else:
        origin = max(hi(b) for b in run)
        termination = min(lo(b) for b in forward)
    return {
        "origin": origin,
        "termination": termination,
        "origin_index": s,
        "displacement_index": i,
        "direction": direction,
    }


# ---------------------------------------------------------------------------
# P-FVG-01 / P-FVG-02
# ---------------------------------------------------------------------------
@feature("fvg")
def f_fvg(ctx: Ctx, tf: str, direction: str, since_index: int = 0, select: str = "latest"):
    if direction is None or since_index is None:
        return None
    gaps = fvg_registry(ctx, tf, direction, since_index)
    if not gaps:
        return None
    if select == "all":
        return gaps
    if select == "latest":
        return gaps[-1]
    if select == "earliest":
        return gaps[0]
    raise MissingParameter(f"unknown fvg selector '{select}'")


def _decisive_beyond(ctx: Ctx, bar, level: float, beyond: str) -> bool:
    """'Decisive close' test. The source uses the words 'decisive close' without defining the
    magnitude (INT-M04-R03, ADV-M06-R03, INT-M11-R04); the definition is a frozen choice."""
    mode = ctx.cfg.require_choice(
        "decisive_close_definition",
        ["body_close_beyond", "body_close_beyond_by_ticks", "full_body_beyond"],
    )
    tick = ctx.cfg.instrument.tick_size
    if mode == "body_close_beyond":
        return bar.close < level if beyond == "below" else bar.close > level
    if mode == "body_close_beyond_by_ticks":
        n = float(ctx.cfg.require("decisive_close_min_ticks"))
        return (bar.close < level - n * tick) if beyond == "below" else (bar.close > level + n * tick)
    return (
        (bar.close < level and bar.open < level)
        if beyond == "below"
        else (bar.close > level and bar.open > level)
    )


@feature("fvg_state")
def f_fvg_state(ctx: Ctx, tf: str, zone: Dict[str, Any]):
    if zone is None:
        return None
    bars = ctx.bars(tf)
    later = bars[zone["index"] + 1 :]
    beyond = "below" if zone["direction"] == "bullish" else "above"
    far = zone["low"] if zone["direction"] == "bullish" else zone["high"]
    state = "unmitigated"
    for b in later:
        if _decisive_beyond(ctx, b, far, beyond):
            return "failed"
        if zone["direction"] == "bullish" and b.low <= zone["high"]:
            state = "partially_mitigated"
        if zone["direction"] == "bearish" and b.high >= zone["low"]:
            state = "partially_mitigated"
    return state


@feature("fvg_inverted")
def f_fvg_inverted(ctx: Ctx, tf: str, zone: Dict[str, Any]):
    """A failed FVG that has since been retested from the opposite side and held.

    The source never defines 'holds' (ADV-M06-R03). Registered as blocking unsupported item
    U-IFVG-HOLD; the caller must record an operationalisation and select the implemented test.
    """
    if zone is None:
        return False
    ctx.cfg.require_operationalisation("U-IFVG-HOLD")
    mode = ctx.cfg.require_choice(
        "inversion_hold_definition", ["retest_then_close_beyond_zone_without_decisive_break"]
    )
    bars = ctx.bars(tf)
    orig = zone["direction"]                      # polarity BEFORE inversion
    beyond = "below" if orig == "bullish" else "above"
    far = zone["low"] if orig == "bullish" else zone["high"]
    fail_at = None
    for i in range(zone["index"] + 1, len(bars)):
        if _decisive_beyond(ctx, bars[i], far, beyond):
            fail_at = i
            break
    if fail_at is None:
        return False
    if mode != "retest_then_close_beyond_zone_without_decisive_break":
        return False
    retested = False
    for b in bars[fail_at + 1 :]:
        if orig == "bullish":                     # inverted -> now resistance
            if b.high >= zone["low"]:
                retested = True
            if retested and b.close < zone["low"]:
                return True
            if b.close > zone["high"]:
                return False
        else:                                     # inverted -> now support
            if b.low <= zone["high"]:
                retested = True
            if retested and b.close > zone["high"]:
                return True
            if b.close < zone["low"]:
                return False
    return False


# ---------------------------------------------------------------------------
# P-OB-01 / P-OB-02
# ---------------------------------------------------------------------------
@feature("order_block")
def f_order_block(ctx: Ctx, tf: str, displacement_index, direction: Optional[str] = None):
    i = _idx(ctx, tf, displacement_index)
    if i is None:
        return None
    ob = order_block_at(ctx, tf, i)
    if ob is None or (direction and ob["direction"] != direction):
        return None
    return ob


@feature("breaker_state")
def f_breaker_state(ctx: Ctx, tf: str, ob: Dict[str, Any]):
    if ob is None:
        return None
    test = ctx.cfg.require_choice("breaker_test", ["body_close", "sweep_plus_mss"])
    cs = ctx.candles(tf)
    later = cs[ob["index"] + 1 :]
    base = P.breaker_or_mitigation(
        P.OrderBlock(ob["direction"], ob["low"], ob["high"], ob["index"]), later
    )
    if test == "body_close" or base != "breaker":
        return base
    # BEG-M06-R03 additionally requires a sweep of the order block and a following MSS opposite
    # the block's original bias.
    opposite = "bearish" if ob["direction"] == "bullish" else "bullish"
    bars = ctx.bars(tf)
    swept = any(
        (b.low < ob["low"]) if ob["direction"] == "bullish" else (b.high > ob["high"])
        for b in bars[ob["index"] + 1 :]
    )
    if not swept:
        return "mitigation"
    for i in range(ob["index"] + 1, len(bars)):
        if f_mss(ctx, tf, at_index=i, direction=opposite):
            return "breaker"
    return "mitigation"


@feature("zone_overlap")
def f_zone_overlap(ctx: Ctx, zone_a, zone_b):
    if zone_a is None or zone_b is None:
        return None
    a = (zone_a["low"], zone_a["high"]) if isinstance(zone_a, dict) else tuple(zone_a)
    b = (zone_b["low"], zone_b["high"]) if isinstance(zone_b, dict) else tuple(zone_b)
    r = P.zones_overlap(a[0], a[1], b[0], b[1])
    return {"low": r[0], "high": r[1]} if r else None


# ---------------------------------------------------------------------------
# P-LIQ-01 / P-LIQ-02
# ---------------------------------------------------------------------------
@feature("liquidity_pools")
def f_liquidity_pools(ctx: Ctx, tf: str, side: str, kinds: Sequence[str],
                      session_window_param: Optional[str] = None, select: str = "all",
                      relative_to_price: bool = True):
    pools = pool_registry(ctx, tf, side, kinds, session_window_param)
    if relative_to_price:
        price = f_bar(ctx, tf, "close")
        pools = [p for p in pools if (p["price"] > price if side == "buy" else p["price"] < price)]
    if select == "all":
        return pools
    if not pools:
        return None
    if select == "nearest":
        price = f_bar(ctx, tf, "close")
        return min(pools, key=lambda p: (abs(p["price"] - price), p["kind"]))
    if select == "furthest":
        price = f_bar(ctx, tf, "close")
        return max(pools, key=lambda p: (abs(p["price"] - price), p["kind"]))
    raise MissingParameter(f"unknown pool selector '{select}'")


@feature("sweep")
def f_sweep(ctx: Ctx, tf: str, level: float, side: str, since_index: int = 0):
    start = _idx(ctx, tf, since_index)
    if level is None or side is None or start is None:
        return None
    s = P.detect_sweep(ctx.candles(tf), level, side, start, ctx.fp())
    if s is None:
        return None
    return {
        "side": s.side,
        "level": s.level,
        "extreme": s.extreme,
        "sweep_index": s.sweep_index,
        "reversal_index": s.reversal_index,
        "classification": s.classification,
    }


@feature("level_reclaimed")
def f_level_reclaimed(ctx: Ctx, tf: str, level: float, side: str, from_index: int,
                      within_bars: Optional[int] = None):
    """Judas reclaim test (BEG-M08-R06). The price test is undefined in the source (CF-14):
    registered as blocking unsupported item U-RECLAIM and supplied as a frozen choice."""
    if level is None:
        return False
    ctx.cfg.require_operationalisation("U-RECLAIM")
    mode = ctx.cfg.require_choice(
        "reclaim_definition",
        ["close_back_beyond_level", "wick_back_beyond_level", "close_back_beyond_level_plus_buffer"],
    )
    n = int(within_bars if within_bars is not None else ctx.cfg.require("sweep_reclaim_bars"))
    bars = ctx.bars(tf)
    start = _idx(ctx, tf, from_index)
    if start is None:
        return False
    seg = bars[start + 1 : start + 1 + n]
    buf = 0.0
    if mode == "close_back_beyond_level_plus_buffer":
        buf = float(ctx.cfg.require("reclaim_buffer"))
    for b in seg:
        if side == "ssl":                                  # pool below; reclaim = back above
            if mode == "wick_back_beyond_level":
                if b.high > level:
                    return True
            elif b.close > level + buf:
                return True
        else:                                              # pool above; reclaim = back below
            if mode == "wick_back_beyond_level":
                if b.low < level:
                    return True
            elif b.close < level - buf:
                return True
    return False


# ---------------------------------------------------------------------------
# P-MSS-01 / P-MSS-02
# ---------------------------------------------------------------------------
@feature("mss")
def f_mss(ctx: Ctx, tf: str, at_index: int = -1, direction: Optional[str] = None):
    cs = ctx.candles(tf)
    i = _idx(ctx, tf, at_index)
    if i is None or not 0 <= i < len(cs):
        return False
    st = structure(ctx, tf, upto_index=i - 1)
    state, gp = st["state"], st["governing_point"]
    if gp is None:
        return False
    if direction == "bullish" and state != "bearish":
        return False
    if direction == "bearish" and state != "bullish":
        return False
    disp = P.is_displacement(cs, i, ctx.fp(), broke_level=gp)
    return P.mss_strict(cs[i], gp, state, disp)


@feature("mss_scope")
def f_mss_scope(ctx: Ctx, tf: str, at_index: int = -1, range_tf: str = "htf"):
    i = _idx(ctx, tf, at_index)
    if i is None or not f_mss(ctx, tf, at_index=i):
        return None
    r = _dealing_range(ctx, range_tf)
    if r is None:
        return "internal"
    c = ctx.candles(tf)[i]
    return "external" if (c.close > r["high"] or c.close < r["low"]) else "internal"


# ---------------------------------------------------------------------------
# P-RANGE-01
# ---------------------------------------------------------------------------
@feature("dealing_range")
def f_dealing_range(ctx: Ctx, tf: str):
    return _dealing_range(ctx, tf)


@feature("pd_location")
def f_pd_location(ctx: Ctx, tf: str, price: Optional[float] = None, price_tf: Optional[str] = None):
    if price is None:
        price = f_bar(ctx, price_tf or tf, "close")
    return _pd_location(ctx, tf, price)


@feature("range_depth_fraction")
def f_range_depth_fraction(ctx: Ctx, tf: str, price: Optional[float] = None,
                           price_tf: Optional[str] = None):
    if price is None:
        price = f_bar(ctx, price_tf or tf, "close")
    return _range_depth_fraction(ctx, tf, price)


# ---------------------------------------------------------------------------
# P-FIB-01
# ---------------------------------------------------------------------------
@feature("fib_levels")
def f_fib_levels(ctx: Ctx, origin: float, termination: float):
    if origin is None or termination is None or origin == termination:
        return None
    f = P.fib_levels(origin, termination, ctx.fp())
    return {
        "origin": f.origin,
        "termination": f.termination,
        "direction": f.direction,
        "eq": f.eq,
        "ote_start": f.ote_start,
        "ote_sweet": f.ote_sweet,
        "ote_end": f.ote_end,
        "ext_27": f.ext_27,
        "ext_62": f.ext_62,
    }


def _fib_obj(fib: Dict[str, Any]):
    return P.FibLevels(
        fib["origin"], fib["termination"], fib["direction"], fib["eq"], fib["ote_start"],
        fib["ote_sweet"], fib["ote_end"], fib["ext_27"], fib["ext_62"],
    )


@feature("in_ote")
def f_in_ote(ctx: Ctx, fib: Dict[str, Any], price: Optional[float] = None, zone=None):
    if fib is None:
        return False
    if zone is not None:
        lo, hi = sorted((fib["ote_start"], fib["ote_end"]))
        z = (zone["low"], zone["high"]) if isinstance(zone, dict) else tuple(zone)
        return P.zones_overlap(lo, hi, z[0], z[1]) is not None
    if price is None:
        return False
    return _fib_obj(fib).in_ote(price)


@feature("retracement_class")
def f_retracement_class(ctx: Ctx, fib: Dict[str, Any], price: float):
    if fib is None or price is None:
        return None
    return _fib_obj(fib).retracement_class(price)


# ---------------------------------------------------------------------------
# P-TIME-01 / P-TIME-02
# ---------------------------------------------------------------------------
@feature("in_session")
def f_in_session(ctx: Ctx, window_param: str):
    return _in_session(ctx, window_param)


@feature("session_range")
def f_session_range(ctx: Ctx, tf: str, window_param: str, occurrence: int = 0):
    return _session_range(ctx, tf, window_param, occurrence)


@feature("period_open")
def f_period_open(ctx: Ctx, period: str, tf: str = "execution"):
    return _period_open(ctx, period, tf)


# ---------------------------------------------------------------------------
# P-BIAS-01 / P-BIAS-02 / P-BIAS-03
# ---------------------------------------------------------------------------
@feature("bias_opening_price")
def f_bias_opening_price(ctx: Ctx, tf: str = "execution"):
    price = f_bar(ctx, tf, "close")
    mo = _period_open(ctx, "monthly", tf)
    wo = _period_open(ctx, "weekly", tf)
    if price is None or mo is None or wo is None:
        return "unclear"
    if price > mo and price > wo:
        return "bullish"
    if price < mo and price < wo:
        return "bearish"
    return "unclear"


@feature("bias_structural")
def f_bias_structural(ctx: Ctx, tf: str, dol_scope: str = "erl"):
    st = structure(ctx, tf)
    direction = st["state"] if st["state"] in ("bullish", "bearish") else "unclear"
    price = f_bar(ctx, tf, "close")
    out = {
        "direction": direction,
        "pd_location": _pd_location(ctx, tf, price),
        "dol": None,
        "invalidation": st["governing_point"],
    }
    if direction != "unclear":
        out["dol"] = f_dol(ctx, direction=direction, scope=dol_scope, tf=tf)
    return out


@feature("bias_daily")
def f_bias_daily(ctx: Ctx, tf: str = "htf", price_tf: str = "execution"):
    method = ctx.cfg.require_choice("daily_bias_method", ["three_factor", "single_mss"])
    if method == "single_mss":
        bars = ctx.bars(tf)
        for i in range(len(bars) - 1, -1, -1):
            if f_mss(ctx, tf, at_index=i, direction="bullish"):
                return "bullish"
            if f_mss(ctx, tf, at_index=i, direction="bearish"):
                return "bearish"
        return "neutral"
    st = structure(ctx, tf)["state"]
    if st not in ("bullish", "bearish"):
        return "neutral"
    price = f_bar(ctx, price_tf, "close")
    day_open = _period_open(ctx, "daily", price_tf)
    if price is None or day_open is None:
        return "neutral"
    open_lean = "bullish" if price > day_open else "bearish" if price < day_open else "neutral"
    draw_side = _unswept_draw_side(ctx, price_tf)
    if st == open_lean == draw_side:
        return st
    return "neutral"


def _unswept_draw_side(ctx: Ctx, tf: str) -> str:
    """Nearest significant unswept pool (previous day / week extremes) as the likely draw."""
    price = f_bar(ctx, tf, "close")
    best, best_side = None, "neutral"
    for side, sign in (("buy", 1), ("sell", -1)):
        for p in pool_registry(ctx, tf, side, ["prev_day", "prev_week"]):
            if p["swept"]:
                continue
            if sign > 0 and p["price"] <= price:
                continue
            if sign < 0 and p["price"] >= price:
                continue
            d = abs(p["price"] - price)
            if best is None or d < best:
                best, best_side = d, "bullish" if side == "buy" else "bearish"
    return best_side


# ---------------------------------------------------------------------------
# P-DOL-01
# ---------------------------------------------------------------------------
_KIND_RANK = {"equal": 0, "prev_month": 1, "prev_week": 1, "prev_day": 2, "session_extreme": 2, "swing": 3}


@feature("dol")
def f_dol(ctx: Ctx, direction: str, scope: str = "erl", tf: str = "htf",
          kinds: Sequence[str] = ("equal", "swing", "prev_day", "prev_week", "prev_month")):
    side = "buy" if direction == "bullish" else "sell"
    price = f_bar(ctx, tf, "close")
    rng = _dealing_range(ctx, tf)
    cands = []
    for p in pool_registry(ctx, tf, side, list(kinds)):
        if p["swept"]:
            continue
        if side == "buy" and p["price"] <= price:
            continue
        if side == "sell" and p["price"] >= price:
            continue
        if rng is None:
            loc = "erl"
        else:
            loc = "erl" if (p["price"] > rng["high"] or p["price"] < rng["low"]) else "irl"
        if scope in ("irl", "erl") and loc != scope:
            continue
        cands.append({**p, "irl_or_erl": loc, "distance": abs(p["price"] - price)})
    if not cands:
        return None
    cands.sort(key=lambda c: (-tf_rank(c["tf"]), _KIND_RANK[c["kind"]], c["distance"], c["price"]))
    return cands[0]


# ---------------------------------------------------------------------------
# P-PO3-01
# ---------------------------------------------------------------------------
@feature("po3_phase")
def f_po3_phase(ctx: Ctx, tf: str, accumulation_window_param: str, period: str = "daily"):
    acc = _session_range(ctx, tf, accumulation_window_param)
    if acc is None:
        return "undetermined"
    bars = ctx.bars(tf)
    after = bars[acc["end_index"] + 1 :]
    if not after:
        return "accumulation"
    pen = float(ctx.cfg.require("sweep_min_penetration"))
    z = int(ctx.cfg.require("sweep_reclaim_bars"))
    up = [i for i, b in enumerate(after) if b.high > acc["high"] + pen]
    dn = [i for i, b in enumerate(after) if b.low < acc["low"] - pen]
    if not up and not dn:
        return "accumulation"
    if up and dn:
        return "failed"                       # both sides taken (INT-M10-R05, ADV-M08-R05)
    breach_i = up[0] if up else dn[0]
    side = "bsl" if up else "ssl"
    level = acc["high"] if up else acc["low"]
    window = after[breach_i : breach_i + z + 1]
    reclaimed = any((b.close < level) if up else (b.close > level) for b in window)
    if not reclaimed:
        return "failed" if len(after) > breach_i + z else "manipulation"
    want = "bearish" if up else "bullish"
    base = acc["end_index"] + 1 + breach_i
    for i in range(base, len(bars)):
        if f_mss(ctx, tf, at_index=i, direction=want):
            return "distribution"
    return "manipulation"


# ---------------------------------------------------------------------------
# P-SMT-01
# ---------------------------------------------------------------------------
@feature("smt_divergence")
def f_smt_divergence(ctx: Ctx, tf: str, side: str, correlated: str):
    """Price-to-price non-confirmation at a shared extreme. Requires a second instrument feed and
    a correlation-stability test the source does not define (registered as U-SMT-CORR)."""
    ctx.cfg.require_operationalisation("U-SMT-CORR")
    window = int(ctx.cfg.require("smt_swing_comparison_window"))
    threshold = float(ctx.cfg.require("smt_correlation_min"))
    sec_view = ctx.view.correlated_view(correlated)
    sec_ctx = Ctx(sec_view, ctx.cfg, ctx.roles)
    a = ctx.bars(tf)[-window:]
    b = sec_ctx.bars(tf)[-window:]
    n = min(len(a), len(b))
    if n < 3:
        return None
    if abs(_corr([x.close for x in a[-n:]], [x.close for x in b[-n:]])) < threshold:
        return None
    swing_side = "low" if side == "sell" else "high"
    pa = swing_registry(ctx, tf, swing_side, "short_term")
    pb = swing_registry(sec_ctx, tf, swing_side, "short_term")
    if len(pa) < 2 or len(pb) < 2:
        return None
    a_new = pa[-1]["price"] < pa[-2]["price"] if swing_side == "low" else pa[-1]["price"] > pa[-2]["price"]
    b_new = pb[-1]["price"] < pb[-2]["price"] if swing_side == "low" else pb[-1]["price"] > pb[-2]["price"]
    if a_new == b_new:
        return None
    preferred = ctx.view.data.instrument if not a_new else correlated
    return {"present": True, "preferred_instrument": preferred,
            "direction": "bullish" if swing_side == "low" else "bearish"}


def _corr(x: List[float], y: List[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        return 0.0
    return sxy / (sxx ** 0.5 * syy ** 0.5)


# ---------------------------------------------------------------------------
# P-RISK-01
# ---------------------------------------------------------------------------
@feature("position_size")
def f_position_size(ctx: Ctx, entry: float, stop: float):
    return P.position_size(
        ctx.equity, entry, stop, ctx.cfg.instrument.value_per_unit_move, ctx.fp()
    )


@feature("r_multiple")
def f_r_multiple(ctx: Ctx, entry: float, stop: float, exit_price: float):
    return P.r_multiple(entry, stop, exit_price)


# ---------------------------------------------------------------------------
# helpers used by selection nodes (pure arithmetic on already-computed values)
# ---------------------------------------------------------------------------
@feature("offset")
def f_offset(ctx: Ctx, price: float, ticks: float, direction: str):
    """Structural stop buffer. 'small buffer' is unspecified in the source (BEG-M11-EX01);
    the tick count is a frozen parameter with no default."""
    if price is None:
        return None
    d = ctx.cfg.instrument.tick_size * float(ticks)
    return price - d if direction == "below" else price + d


@feature("midpoint")
def f_midpoint(ctx: Ctx, zone):
    if zone is None:
        return None
    if isinstance(zone, dict):
        return (zone["low"] + zone["high"]) / 2.0
    return (zone[0] + zone[1]) / 2.0


@feature("pick")
def f_pick(ctx: Ctx, values: Sequence[Any], mode: str):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    if mode == "min":
        return min(vals)
    if mode == "max":
        return max(vals)
    raise MissingParameter(f"unknown pick mode '{mode}'")
