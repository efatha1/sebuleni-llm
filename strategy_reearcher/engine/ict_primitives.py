"""
ict_primitives.py — reference implementation of the detection primitives in primitives.json.

Design rules (enforced in code, not just in prose):
  * Anything the knowledge base specifies is implemented literally (three-candle swing test,
    FVG geometry, CE = 50% of gap, EQ = (H+L)/2, OTE 0.62/0.705/0.79, extensions -0.27/-0.62 ...).
  * Anything the knowledge base leaves UNSPECIFIED is a *required* parameter with NO default.
    Calling a function without it raises `UnspecifiedParameter`. The caller must freeze the value
    in a FrozenParams object before any label is produced (ADV-M18-R02, ADV-M18-C03) and report it
    as a research parameter, never as ICT doctrine (ADV-M18-R01).
  * Labels are timestamped at the candle whose close completes the pattern (ADV-M18-R04
    look-ahead control): swing points confirm one candle late; FVG at candle 3; MSS at the
    breaking close.

Every function carries the knowledge-base object ids it implements in its docstring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")  # BEG-M08-R05: all windows anchored to New York time


class UnspecifiedParameter(ValueError):
    """Raised when a knowledge-base-unspecified parameter has not been frozen by the researcher."""


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    time: Optional[datetime] = None

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open


@dataclass
class FrozenParams:
    """Researcher-frozen values for knowledge-base-unspecified parameters.

    Each field maps to an entry in parameter_register.json. None means 'not frozen';
    functions that need it will raise UnspecifiedParameter. No defaults are supplied on purpose.
    """
    displacement_range_multiple: Optional[float] = None      # BEG-M05-R01 (unspecified)
    displacement_lookback: Optional[int] = None               # BEG-M05-R01 (unspecified)
    displacement_body_ratio_min: Optional[float] = None       # BEG-M05-C01/C02 heuristic 60-70%, unfixed (BEG-M05-AMB01)
    equal_level_tolerance: Optional[float] = None             # BEG-M04-C05 heuristic 5-10 pips fx, unfixed
    sweep_min_penetration: Optional[float] = None             # ADV-M18-C03 parameter 'Y'
    sweep_reclaim_bars: Optional[int] = None                  # BEG-M08-R06 ~2-3 (Judas) / BEG-M09-R02 unspecified / ADV-M18-C03 'Z'
    fib_anchor: Optional[str] = None                          # 'body' (BEG-M07-R01) | 'wick' (INT-M07-R01) — CF-01
    ote_levels: Optional[Tuple[float, float, float]] = None   # (0.62, 0.705, 0.79) BEG-M07-R03 | (0.618, None, 0.786) INT-M07-R02 — CF-02
    london_open_kz: Optional[Tuple[time, time]] = None        # BEG-M08-R02 alternatives — CF-03
    new_york_open_kz: Optional[Tuple[time, time]] = None      # BEG-M08-R04 alternatives — CF-03
    asian_window: Optional[Tuple[time, time]] = None          # BEG-M08-R01 / INT-M09-R01 alternatives
    london_close_kz: Optional[Tuple[time, time]] = None       # BEG-M08-R03 non-overlapping alternatives
    risk_fraction: Optional[float] = None                     # ranges only: BEG-M13-R01 / INT-M12-R01 / ADV-M17-R02 — CF-07

    def require(self, name: str):
        v = getattr(self, name)
        if v is None:
            raise UnspecifiedParameter(
                f"'{name}' is unspecified in the knowledge base; freeze it in FrozenParams "
                f"before labeling (see parameter_register.json)."
            )
        return v


# --------------------------------------------------------------------------------------
# P-SWING-01 — Swing High / Swing Low (BEG-M01-C01, BEG-M01-C02)
# --------------------------------------------------------------------------------------
def swing_highs(highs: Sequence[float]) -> List[int]:
    """Indices i where highs[i] > highs[i-1] and highs[i] > highs[i+1]. Confirmed at i+1."""
    return [i for i in range(1, len(highs) - 1) if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]]


def swing_lows(lows: Sequence[float]) -> List[int]:
    """Indices i where lows[i] < lows[i-1] and lows[i] < lows[i+1]. Confirmed at i+1."""
    return [i for i in range(1, len(lows) - 1) if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]]


# --------------------------------------------------------------------------------------
# P-SWING-02 — Intermediate-term swings (INT-M01-R01)
# --------------------------------------------------------------------------------------
def intermediate_term_highs(sth_values: Sequence[float]) -> List[int]:
    """An ITH is an STH with lower STHs on both its left and right (INT-M01-R01)."""
    return [i for i in range(1, len(sth_values) - 1)
            if sth_values[i] > sth_values[i - 1] and sth_values[i] > sth_values[i + 1]]


def intermediate_term_lows(stl_values: Sequence[float]) -> List[int]:
    """An ITL is an STL with higher STLs on both sides (INT-M01-R01)."""
    return [i for i in range(1, len(stl_values) - 1)
            if stl_values[i] < stl_values[i - 1] and stl_values[i] < stl_values[i + 1]]


# --------------------------------------------------------------------------------------
# P-STRUCT-01 — Structure state & governing point (BEG-M03-C01..C04, BEG-M03-C02)
# --------------------------------------------------------------------------------------
def structure_state(swing_high_values: Sequence[float], swing_low_values: Sequence[float]) -> str:
    """'bullish' if the last two consecutive swing-high comparisons and the last two swing-low
    comparisons are both rising (>= 2 HH and >= 2 HL, BEG-M03-C03); 'bearish' if both falling
    (BEG-M03-C04); otherwise 'range'."""
    def last_two(seq: Sequence[float], cmp) -> bool:
        return len(seq) >= 3 and cmp(seq[-1], seq[-2]) and cmp(seq[-2], seq[-3])

    up = lambda a, b: a > b
    dn = lambda a, b: a < b
    if last_two(swing_high_values, up) and last_two(swing_low_values, up):
        return "bullish"
    if last_two(swing_high_values, dn) and last_two(swing_low_values, dn):
        return "bearish"
    return "range"


def governing_point(state: str, swing_high_values: Sequence[float], swing_low_values: Sequence[float]) -> Optional[float]:
    """Bullish -> most recent confirmed higher low; bearish -> most recent lower high (BEG-M03-C02)."""
    if state == "bullish":
        return swing_low_values[-1]
    if state == "bearish":
        return swing_high_values[-1]
    return None


# --------------------------------------------------------------------------------------
# P-DISP-01 — Displacement (BEG-M05-R01, INT-M03-R01)
# --------------------------------------------------------------------------------------
def is_displacement(candles: Sequence[Candle], i: int, params: FrozenParams,
                    broke_level: Optional[float] = None) -> bool:
    """All four BEG-M05-R01 criteria. Criteria 1-3 need frozen thresholds (unspecified in KB).
    Criterion 4 (must break a meaningful swing) is checked when `broke_level` is supplied."""
    mult = params.require("displacement_range_multiple")
    lb = params.require("displacement_lookback")
    ratio = params.require("displacement_body_ratio_min")
    c = candles[i]
    if i - lb < 0:
        return False
    recent = candles[i - lb:i]
    avg_range = sum(x.range for x in recent) / len(recent)
    if c.range == 0 or c.range < mult * avg_range:                       # (1) unusually large range
        return False
    if c.body / c.range < ratio:                                         # (2) body dominates range
        return False
    prev = candles[i - 1]
    if c.bullish and c.close <= prev.high:                               # (3) no significant overlap
        return False
    if c.bearish and c.close >= prev.low:
        return False
    if broke_level is not None:                                          # (4) actually breaks structure
        if c.bullish and not (c.close > broke_level):
            return False
        if c.bearish and not (c.close < broke_level):
            return False
    return True


# --------------------------------------------------------------------------------------
# P-FVG-01 — Fair Value Gap + Consequent Encroachment (BEG-M05-R02, INT-M04-R01, INT-M04-R02)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FVG:
    direction: str      # 'bullish' | 'bearish'
    low: float
    high: float
    index: int          # index of candle 3 (label timestamp)

    @property
    def ce(self) -> float:
        return (self.low + self.high) / 2.0     # INT-M04-R02: CE = 50% midpoint


def fvg(c1: Candle, c2: Candle, c3: Candle, index: int = 2) -> Optional[FVG]:
    """Bullish: low(c3) > high(c1) -> zone [high(c1), low(c3)]. Bearish: high(c3) < low(c1) ->
    zone [high(c3), low(c1)]. Touching/overlapping wicks -> no FVG (INT-M04-R01).
    Note: the displacement quality of c2 (BEG-M05-R03) is checked separately via is_displacement."""
    if c3.low > c1.high:
        return FVG("bullish", c1.high, c3.low, index)
    if c3.high < c1.low:
        return FVG("bearish", c3.high, c1.low, index)
    return None


def fvg_state(gap: FVG, later: Iterable[Candle]) -> str:
    """P-FVG-02 mitigation state: 'unmitigated' | 'partially_mitigated' | 'failed'.
    Failed = body CLOSE through the far side (INT-M04-R03, ADV-M06-R03). 'Decisive' is
    unspecified in the KB; this implementation uses any close beyond the far side — report it."""
    state = "unmitigated"
    for c in later:
        if gap.direction == "bullish":
            if c.close < gap.low:
                return "failed"
            if c.low <= gap.high:
                state = "partially_mitigated"
        else:
            if c.close > gap.high:
                return "failed"
            if c.high >= gap.low:
                state = "partially_mitigated"
    return state


# --------------------------------------------------------------------------------------
# P-OB-01 — Order Block (BEG-M06-C01, INT-M05-C01)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class OrderBlock:
    direction: str
    low: float
    high: float
    index: int


def order_block(candles: Sequence[Candle], displacement_index: int) -> Optional[OrderBlock]:
    """Bullish OB = last down-close candle immediately before a bullish displacement; bearish OB =
    last up-close candle before a bearish displacement. Zone = that candle's full high-low range."""
    d = candles[displacement_index]
    for j in range(displacement_index - 1, -1, -1):
        c = candles[j]
        if d.bullish and c.bearish:
            return OrderBlock("bullish", c.low, c.high, j)
        if d.bearish and c.bullish:
            return OrderBlock("bearish", c.low, c.high, j)
    return None


def breaker_or_mitigation(ob: OrderBlock, later: Iterable[Candle]) -> str:
    """P-OB-02 observable test (INT-M05-R02): body close through the far boundary -> 'breaker'
    (inverted polarity); return into zone without such a close -> 'mitigation'; no touch -> 'untested'.
    BEG-M06-R03 additionally requires sweep + MSS for a Breaker — layer that check separately (CT-16)."""
    touched = False
    for c in later:
        if ob.direction == "bullish":
            if c.close < ob.low:
                return "breaker"
            if c.low <= ob.high:
                touched = True
        else:
            if c.close > ob.high:
                return "breaker"
            if c.high >= ob.low:
                touched = True
    return "mitigation" if touched else "untested"


def zones_overlap(a_low: float, a_high: float, b_low: float, b_high: float) -> Optional[Tuple[float, float]]:
    """Confluence overlap of two PD arrays (BEG-M06-R01, INT-M05-R04). Returns the overlap or None."""
    lo, hi = max(a_low, b_low), min(a_high, b_high)
    return (lo, hi) if lo <= hi else None


# --------------------------------------------------------------------------------------
# P-LIQ-01 — Equal highs / lows (BEG-M04-C05, BEG-M04-C06, INT-M02-R01)
# --------------------------------------------------------------------------------------
def equal_levels(values: Sequence[float], params: FrozenParams) -> List[List[float]]:
    """Groups of >= 2 swing values within the frozen tolerance (tolerance is unspecified in the KB)."""
    tol = params.require("equal_level_tolerance")
    groups: List[List[float]] = []
    for v in values:
        for g in groups:
            if abs(v - g[0]) <= tol:
                g.append(v)
                break
        else:
            groups.append([v])
    return [g for g in groups if len(g) >= 2]


# --------------------------------------------------------------------------------------
# P-LIQ-02 — Sweep / raid (BEG-M04-C08, INT-M02-R05, BEG-M08-R06, ADV-M18-C03)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Sweep:
    side: str          # 'ssl' (below a low) | 'bsl' (above a high)
    level: float
    extreme: float
    sweep_index: int
    reversal_index: Optional[int]   # first close back on the original side of the level within Z bars
    classification: str             # 'raid' | 'continuation' | 'pending'


def detect_sweep(candles: Sequence[Candle], level: float, side: str, start: int, params: FrozenParams) -> Optional[Sweep]:
    """Sweep = price trades at least Y beyond the pool and then closes back through the level within
    Z bars (raid); if no reclaim within Z bars -> 'continuation' (INT-M02-R05). Y and Z are the KB's
    own research-template parameters (ADV-M18-C03) and must be frozen."""
    y = params.require("sweep_min_penetration")
    z = params.require("sweep_reclaim_bars")
    for i in range(start, len(candles)):
        c = candles[i]
        pierced = (side == "ssl" and c.low < level - y) or (side == "bsl" and c.high > level + y)   # strictly BEYOND the level (BEG-M04-C08)
        if not pierced:
            continue
        extreme = c.low if side == "ssl" else c.high
        for k in range(i, min(i + z + 1, len(candles))):
            ck = candles[k]
            extreme = min(extreme, ck.low) if side == "ssl" else max(extreme, ck.high)
            back = (side == "ssl" and ck.close > level) or (side == "bsl" and ck.close < level)
            if back:
                return Sweep(side, level, extreme, i, k, "raid")
        cls = "continuation" if i + z < len(candles) else "pending"
        return Sweep(side, level, extreme, i, None, cls)
    return None


# --------------------------------------------------------------------------------------
# P-MSS-01 — strict Market Structure Shift (BEG-M03-R01, BEG-M03-R02, INT-M03-R02)
# --------------------------------------------------------------------------------------
def mss_strict(candle: Candle, governing_level: float, prior_state: str, displacement_ok: bool) -> bool:
    """Bearish MSS: prior bullish structure and body CLOSE below the governing low; bullish MSS: prior
    bearish structure and body close above the governing high. Displacement is required by the book's
    working definition (BEG-M03-R02); wick-only breaches never qualify (BEG-M03-R01)."""
    if not displacement_ok:
        return False
    if prior_state == "bullish":
        return candle.close < governing_level
    if prior_state == "bearish":
        return candle.close > governing_level
    return False


# --------------------------------------------------------------------------------------
# P-RANGE-01 — Dealing range / equilibrium / premium-discount (INT-M06-R02, INT-M01-R03)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class DealingRange:
    high: float
    low: float

    @property
    def equilibrium(self) -> float:
        return (self.high + self.low) / 2.0                     # INT-M06-R02

    def location(self, price: float) -> str:
        if price > self.equilibrium:
            return "premium"
        if price < self.equilibrium:
            return "discount"
        return "equilibrium"

    def depth_fraction(self, price: float) -> float:
        """0 at range low, 1 at range high. INT-M06-R02: outer ~20-25% is the 'deep' zone."""
        return (price - self.low) / (self.high - self.low)


# --------------------------------------------------------------------------------------
# P-FIB-01 — ICT Fibonacci / OTE (BEG-M07-R01, BEG-M07-R03, INT-M07-R02)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class FibLevels:
    origin: float          # 100%
    termination: float     # 0%
    direction: str
    eq: float              # 50%
    ote_start: float       # 62%
    ote_sweet: Optional[float]  # 70.5% (None if the 0.618/0.786 convention is frozen)
    ote_end: float         # 79%
    ext_27: float          # -27%
    ext_62: float          # -62%

    def in_ote(self, price: float) -> bool:
        lo, hi = sorted((self.ote_start, self.ote_end))
        return lo <= price <= hi

    def retracement_class(self, price: float) -> str:
        """INT-M07-R05: shallow (<=50%), standard (62-79%), deep (>79%)."""
        r = abs(price - self.termination) / abs(self.origin - self.termination)
        if r <= 0.50:
            return "shallow"
        if r < 0.62:
            return "between_50_and_62"
        if r <= 0.79:
            return "standard"
        return "deep"


def fib_levels(origin: float, termination: float, params: FrozenParams) -> FibLevels:
    """origin = 100% (leg start), termination = 0% (leg end). Level constants must be frozen
    (CF-02). Anchor price type (body vs wick) is the caller's responsibility (CF-01) — pass the
    prices consistent with params.fib_anchor."""
    params.require("fib_anchor")
    l62, l705, l79 = params.require("ote_levels")
    span = termination - origin
    lvl = lambda r: termination - r * span
    return FibLevels(
        origin=origin, termination=termination,
        direction="bullish" if span > 0 else "bearish",
        eq=lvl(0.50), ote_start=lvl(l62), ote_sweet=(lvl(l705) if l705 is not None else None), ote_end=lvl(l79),
        ext_27=lvl(-0.27), ext_62=lvl(-0.62),
    )


# --------------------------------------------------------------------------------------
# P-TIME-01 / P-TIME-02 — Kill zones and Asian range (BEG-M08-R01..R05)
# --------------------------------------------------------------------------------------
def in_window(t: datetime, window: Tuple[time, time]) -> bool:
    """True if t (tz-aware) falls inside [start, end) expressed in New York local time
    (BEG-M08-R05: anchored to New York; DST handled by the zone conversion)."""
    if t.tzinfo is None:
        raise ValueError("datetime must be tz-aware (convert broker server time first — INT-M09-R02)")
    ny = t.astimezone(NY).time()
    s, e = window
    return s <= ny < e if s < e else (ny >= s or ny < e)   # wraps midnight (Asian 20:00-00:00)


def asian_range(candles: Sequence[Candle], params: FrozenParams) -> Optional[Tuple[float, float]]:
    """High and low of the frozen Asian window (BEG-M08-C03). Look-ahead control: call only with
    candles whose time is inside the window and which have closed."""
    w = params.require("asian_window")
    inside = [c for c in candles if c.time is not None and in_window(c.time, w)]
    if not inside:
        return None
    return max(c.high for c in inside), min(c.low for c in inside)


# --------------------------------------------------------------------------------------
# P-RISK-01 — Position sizing (INT-M12-R01, ADV-M17-R02)
# --------------------------------------------------------------------------------------
def position_size(equity: float, entry: float, stop: float, value_per_unit_move: float, params: FrozenParams) -> float:
    """Size = (equity x risk_fraction) / (|entry - stop| x value per unit price move).
    Risk fraction must be frozen (KB gives ranges only, CF-07)."""
    rf = params.require("risk_fraction")
    dist = abs(entry - stop)
    if dist == 0:
        raise ValueError("stop equals entry — stop must sit beyond a structural premise (P-STOP-01)")
    return (equity * rf) / (dist * value_per_unit_move)


def r_multiple(entry: float, stop: float, exit_price: float) -> float:
    """Outcome in R units (ADV-M18-R06). Recorded, never used as a primary filter (ADV-M17-R04)."""
    risk = abs(entry - stop)
    return (exit_price - entry) / risk if entry > stop else (entry - exit_price) / risk
