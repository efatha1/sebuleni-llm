"""Market-state calculations (see requirements/market_state_requirements.json).

Every function here is a pure function of a `View` (bars visible at the decision bar) plus the
frozen configuration. Nothing is carried forward between bars, which is what makes the
look-ahead control and the determinism contract provable rather than asserted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ._kb import NY, P, Candle
from .data import Bar, TIMEFRAME_ORDER, View, canonical_json, tf_rank
from .errors import MissingData, MissingParameter
from .freeze import FrozenConfig, parse_window


# ---------------------------------------------------------------------------
# Evaluation context
# ---------------------------------------------------------------------------
@dataclass
class Ctx:
    view: View
    cfg: FrozenConfig
    roles: Dict[str, str]
    bindings: Dict[str, Any] = field(default_factory=dict)
    equity: float = 0.0
    _cache: Dict[str, Any] = field(default_factory=dict)

    def tf(self, role_or_tf: str) -> str:
        if role_or_tf in self.roles:
            return self.roles[role_or_tf]
        if role_or_tf in TIMEFRAME_ORDER:
            return role_or_tf
        raise MissingData(f"timeframe role '{role_or_tf}' is not bound in this configuration")

    def bars(self, role_or_tf: str) -> List[Bar]:
        return self.view.bars(self.tf(role_or_tf))

    def candles(self, role_or_tf: str) -> List[Candle]:
        return self.view.candles(self.tf(role_or_tf))

    def fp(self):
        key = "~fp~"
        if key not in self._cache:
            self._cache[key] = self.cfg.frozen_params()
        return self._cache[key]

    def memo(self, key: Tuple, produce):
        k = canonical_json(list(key))
        if k not in self._cache:
            self._cache[k] = produce()
        return self._cache[k]

    @property
    def now(self) -> datetime:
        return self.view.cutoff


# ---------------------------------------------------------------------------
# swing_registry (P-SWING-01 / P-SWING-02)
# ---------------------------------------------------------------------------
def swing_registry(ctx: Ctx, tf: str, side: str, tier: str) -> List[Dict[str, Any]]:
    """Confirmed swing points. `side` in {'high','low'}; `tier` in
    {'short_term','intermediate','long_term'}."""

    def produce():
        bars = ctx.bars(tf)
        vals = [b.high for b in bars] if side == "high" else [b.low for b in bars]
        idx = P.swing_highs(vals) if side == "high" else P.swing_lows(vals)
        st = [{"index": i, "price": vals[i], "confirmed_at_index": i + 1} for i in idx]
        if tier == "short_term":
            return st
        prices = [s["price"] for s in st]
        it_idx = (
            P.intermediate_term_highs(prices) if side == "high" else P.intermediate_term_lows(prices)
        )
        inter = [
            {
                "index": st[i]["index"],
                "price": st[i]["price"],
                "confirmed_at_index": st[i + 1]["confirmed_at_index"],
            }
            for i in it_idx
        ]
        if tier == "intermediate":
            return inter
        if tier == "long_term":
            p2 = [s["price"] for s in inter]
            lt_idx = (
                P.intermediate_term_highs(p2) if side == "high" else P.intermediate_term_lows(p2)
            )
            return [
                {
                    "index": inter[i]["index"],
                    "price": inter[i]["price"],
                    "confirmed_at_index": inter[i + 1]["confirmed_at_index"],
                }
                for i in lt_idx
            ]
        raise MissingParameter(f"unknown swing tier '{tier}'")

    return ctx.memo(("swing_registry", ctx.tf(tf), side, tier), produce)


def _tier(ctx: Ctx) -> str:
    return ctx.cfg.require_choice(
        "governing_swing_tier", ["short_term", "intermediate", "long_term"]
    )


# ---------------------------------------------------------------------------
# structure (P-STRUCT-01)
# ---------------------------------------------------------------------------
def structure(ctx: Ctx, tf: str, upto_index: Optional[int] = None) -> Dict[str, Any]:
    tier = _tier(ctx)

    def produce():
        highs = swing_registry(ctx, tf, "high", tier)
        lows = swing_registry(ctx, tf, "low", tier)
        if upto_index is not None:
            highs = [h for h in highs if h["confirmed_at_index"] <= upto_index]
            lows = [l for l in lows if l["confirmed_at_index"] <= upto_index]
        hv = [h["price"] for h in highs]
        lv = [l["price"] for l in lows]
        state = P.structure_state(hv, lv)
        gp = P.governing_point(state, hv, lv)
        return {"state": state, "governing_point": gp, "highs": hv, "lows": lv}

    return ctx.memo(("structure", ctx.tf(tf), tier, upto_index), produce)


# ---------------------------------------------------------------------------
# controlling_range (P-RANGE-01)
# ---------------------------------------------------------------------------
def dealing_range(ctx: Ctx, tf: str) -> Optional[Dict[str, float]]:
    tier = _tier(ctx)

    def produce():
        highs = swing_registry(ctx, tf, "high", tier)
        lows = swing_registry(ctx, tf, "low", tier)
        if not highs or not lows:
            return None
        hi = highs[-1]["price"]
        lo = lows[-1]["price"]
        if hi <= lo:
            return None
        r = P.DealingRange(hi, lo)
        return {"high": r.high, "low": r.low, "equilibrium": r.equilibrium}

    return ctx.memo(("dealing_range", ctx.tf(tf), tier), produce)


def pd_location(ctx: Ctx, tf: str, price: float) -> Optional[str]:
    r = dealing_range(ctx, tf)
    if r is None or price is None:
        return None
    return P.DealingRange(r["high"], r["low"]).location(price)


def range_depth_fraction(ctx: Ctx, tf: str, price: float) -> Optional[float]:
    r = dealing_range(ctx, tf)
    if r is None or price is None:
        return None
    return P.DealingRange(r["high"], r["low"]).depth_fraction(price)


# ---------------------------------------------------------------------------
# session_calendar (P-TIME-01 / P-TIME-02)
# ---------------------------------------------------------------------------
def in_session(ctx: Ctx, window_param: str) -> bool:
    window = ctx.cfg.window(window_param)
    return P.in_window(ctx.now, window)


def session_blocks(ctx: Ctx, tf: str, window_param: str) -> List[Tuple[int, int]]:
    """Index ranges of *completed* occurrences of the window, oldest first.

    A block is completed only once a visible bar outside the window follows it; an in-progress
    window is never returned, so no decision can consume a range that is not yet final.
    """
    window = ctx.cfg.window(window_param)

    def produce():
        bars = ctx.bars(tf)
        blocks: List[Tuple[int, int]] = []
        cur: Optional[List[int]] = None
        for i, b in enumerate(bars):
            if P.in_window(b.close_time, window):
                if cur is None:
                    cur = [i, i]
                else:
                    cur[1] = i
            elif cur is not None:
                blocks.append((cur[0], cur[1]))
                cur = None
        return blocks

    return ctx.memo(("session_blocks", ctx.tf(tf), window_param, str(window)), produce)


def session_range(ctx: Ctx, tf: str, window_param: str, occurrence: int = 0) -> Optional[Dict[str, Any]]:
    """`occurrence` 0 = most recent completed window."""
    blocks = session_blocks(ctx, tf, window_param)
    if len(blocks) <= occurrence:
        return None
    s, e = blocks[-1 - occurrence]
    bars = ctx.bars(tf)
    seg = bars[s : e + 1]
    return {
        "high": max(b.high for b in seg),
        "low": min(b.low for b in seg),
        "start_index": s,
        "end_index": e,
    }


# ---------------------------------------------------------------------------
# period_opens (P-BIAS-01 / ADV-M07-C03)
# ---------------------------------------------------------------------------
def _ny(dt: datetime) -> datetime:
    return dt.astimezone(NY)


def _period_key(dt: datetime, period: str):
    n = _ny(dt)
    if period == "daily":
        return (n.year, n.month, n.day)
    if period == "weekly":
        iso = n.isocalendar()
        return (iso[0], iso[1])
    if period == "monthly":
        return (n.year, n.month)
    raise MissingParameter(f"unknown period '{period}'")


def period_open(ctx: Ctx, period: str, tf: str = "execution") -> Optional[float]:
    """Opening price of the current period. Known at period start, so no look-ahead."""
    if period == "daily":
        mode = ctx.cfg.require_choice(
            "daily_open_definition", ["new_york_midnight", "instrument_daily_open"]
        )
        if mode == "instrument_daily_open":
            return _instrument_period_open(ctx, "1d")

    def produce():
        bars = ctx.bars(tf)
        if not bars:
            return None
        key = _period_key(ctx.now, period)
        for b in bars:
            if _period_key(b.open_time, period) == key:
                return b.open
        return None

    return ctx.memo(("period_open", period, ctx.tf(tf)), produce)


def _instrument_period_open(ctx: Ctx, tf: str) -> Optional[float]:
    """Open of the in-progress bar on `tf`. Uses open_time, not close_time: a bar's opening
    price is known the moment the period starts, which is what ADV-M07-C03 refers to."""
    series = ctx.view.data.require(tf)
    chosen = None
    for b in series.bars:
        if b.open_time <= ctx.now:
            chosen = b
        else:
            break
    return chosen.open if chosen else None


def previous_period_extreme(ctx: Ctx, period: str, side: str, tf: str = "execution") -> Optional[float]:
    def produce():
        bars = ctx.bars(tf)
        if not bars:
            return None
        cur = _period_key(ctx.now, period)
        prev_key = None
        seg: List[Bar] = []
        for b in bars:
            k = _period_key(b.open_time, period)
            if k == cur:
                continue
            if prev_key != k:
                prev_key, seg = k, []
            seg.append(b)
        if not seg:
            return None
        return max(b.high for b in seg) if side == "high" else min(b.low for b in seg)

    return ctx.memo(("prev_period_extreme", period, side, ctx.tf(tf)), produce)


# ---------------------------------------------------------------------------
# pool_registry (P-LIQ-01)
# ---------------------------------------------------------------------------
POOL_KINDS = ["swing", "equal", "session_extreme", "prev_day", "prev_week", "prev_month"]


def pool_registry(
    ctx: Ctx, tf: str, side: str, kinds: Sequence[str], session_window_param: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Marked liquidity pools on `side` ('buy' = above price, 'sell' = below price)."""
    for k in kinds:
        if k not in POOL_KINDS:
            raise MissingParameter(f"unknown pool kind '{k}'")
    swing_side = "high" if side == "buy" else "low"
    tier = _tier(ctx)

    def produce():
        bars = ctx.bars(tf)
        pools: List[Dict[str, Any]] = []
        if "swing" in kinds:
            for s in swing_registry(ctx, tf, swing_side, tier):
                pools.append(
                    {"price": s["price"], "kind": "swing", "tf": ctx.tf(tf),
                     "from_index": s["confirmed_at_index"]}
                )
        if "equal" in kinds:
            sw = swing_registry(ctx, tf, swing_side, tier)
            groups = P.equal_levels([s["price"] for s in sw], ctx.fp())
            for g in groups:
                price = max(g) if side == "buy" else min(g)
                last_i = max(s["confirmed_at_index"] for s in sw if s["price"] in g)
                pools.append(
                    {"price": price, "kind": "equal", "tf": ctx.tf(tf), "from_index": last_i}
                )
        if "session_extreme" in kinds:
            if session_window_param is None:
                raise MissingParameter("pool kind 'session_extreme' needs session_window_param")
            sr = session_range(ctx, tf, session_window_param)
            if sr is not None:
                pools.append(
                    {
                        "price": sr["high"] if side == "buy" else sr["low"],
                        "kind": "session_extreme",
                        "tf": ctx.tf(tf),
                        "from_index": sr["end_index"] + 1,
                    }
                )
        for period, kind in (("daily", "prev_day"), ("weekly", "prev_week"), ("monthly", "prev_month")):
            if kind in kinds:
                v = previous_period_extreme(ctx, period, swing_side, tf)
                if v is not None:
                    pools.append({"price": v, "kind": kind, "tf": ctx.tf(tf), "from_index": 0})

        for p in pools:
            seg = bars[p["from_index"]:]
            if side == "buy":
                p["swept"] = any(b.high > p["price"] for b in seg)
            else:
                p["swept"] = any(b.low < p["price"] for b in seg)
        pools.sort(key=lambda p: (p["price"], p["kind"], p["from_index"]))
        return pools

    return ctx.memo(("pool_registry", ctx.tf(tf), side, list(kinds), session_window_param, tier), produce)


# ---------------------------------------------------------------------------
# array_registry (P-FVG-01 / P-OB-01)
# ---------------------------------------------------------------------------
def fvg_registry(ctx: Ctx, tf: str, direction: str, since_index: int = 0) -> List[Dict[str, Any]]:
    """Fair value gaps whose middle candle qualifies as displacement (BEG-M05-R03)."""

    def produce():
        cs = ctx.candles(tf)
        out: List[Dict[str, Any]] = []
        for i in range(max(2, since_index + 2), len(cs)):
            g = P.fvg(cs[i - 2], cs[i - 1], cs[i], i)
            if g is None or g.direction != direction:
                continue
            if not P.is_displacement(cs, i - 1, ctx.fp()):
                continue
            out.append(
                {
                    "direction": g.direction,
                    "low": g.low,
                    "high": g.high,
                    "ce": g.ce,
                    "index": i,
                    "displacement_index": i - 1,
                }
            )
        return out

    return ctx.memo(("fvg_registry", ctx.tf(tf), direction, since_index), produce)


def order_block_at(ctx: Ctx, tf: str, displacement_index: int) -> Optional[Dict[str, Any]]:
    cs = ctx.candles(tf)
    if displacement_index >= len(cs):
        return None
    ob = P.order_block(cs, displacement_index)
    if ob is None:
        return None
    return {"direction": ob.direction, "low": ob.low, "high": ob.high, "index": ob.index}


# ---------------------------------------------------------------------------
# risk_state (P-RISK-01)
# ---------------------------------------------------------------------------
@dataclass
class RiskState:
    equity: float
    session_key: Optional[Tuple] = None
    risk_committed_today: float = 0.0
    realised_loss_today: float = 0.0

    def roll(self, key: Tuple):
        if key != self.session_key:
            self.session_key = key
            self.risk_committed_today = 0.0
            self.realised_loss_today = 0.0

    def halted(self, cfg: FrozenConfig) -> bool:
        ceiling = cfg.params.get("max_daily_risk")
        limit = cfg.params.get("daily_loss_limit")
        if ceiling is not None and self.risk_committed_today >= float(ceiling) * self.equity:
            return True
        if limit is not None and self.realised_loss_today >= float(limit) * self.equity:
            return True
        return False
