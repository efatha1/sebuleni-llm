"""Deterministic synthetic scenarios used by the validation tests.

These are not market data. Each scenario is a hand-built bar sequence containing exactly the
structures a compiled strategy names, so the tests can assert that the engine finds them, finds
them at the expected bar, and finds them identically on every run.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Sequence
from zoneinfo import ZoneInfo

from strategy_compiler.engine.data import Bar, MarketData, Series

NY = ZoneInfo("America/New_York")


def bar(t: datetime, minutes: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(open_time=t, close_time=t + timedelta(minutes=minutes),
               open=o, high=h, low=l, close=c)


def zigzag(t0: datetime, minutes: int, start: float, legs: Sequence[float],
           per_leg: int, wick: float) -> List[Bar]:
    """Piecewise-linear bars through `legs`.

    The final bar of each leg overshoots by an extra wick so that the turning point is a strict
    three-candle swing: without the overshoot the pivot bar and its neighbour share the same
    extreme and the swing test (which is strict) finds nothing.
    """
    bars: List[Bar] = []
    prev, t = start, t0
    for target in legs:
        for k in range(1, per_leg + 1):
            o = prev if k == 1 else bars[-1].close
            c = prev + (target - prev) * k / per_leg
            h, l = max(o, c) + wick, min(o, c) - wick
            if k == per_leg:
                if target > o:
                    h += 3 * wick
                else:
                    l -= 3 * wick
            bars.append(bar(t, minutes, o, h, l, c))
            t += timedelta(minutes=minutes)
        prev = target
    return bars


def _append(bars: List[Bar], minutes: int, o, h, l, c) -> None:
    bars.append(bar(bars[-1].close_time, minutes, o, h, l, c))


def long_sweep_displacement_scenario() -> MarketData:
    """Bullish raid -> displacement + MSS -> fair value gap -> retracement to CE -> rally.

    Five-minute layout, in order:
      * rising warm-up, then a decline printing three lower highs and three lower lows;
      * one candle that pierces the last swing low (1.08100) and closes back above it — the raid;
      * a small candle (c1) whose high defines the lower edge of the gap;
      * a large-bodied bullish candle (c2) closing above the governing lower high — displacement
        and MSS on the same bar, exactly as the specification's steps 4 and 5 describe;
      * c3, whose low stays above c1's high, so the gap is [1.08100, 1.08600] and CE is 1.08350;
      * an extension that places the gap inside the 62-79% retracement band;
      * a controlled pullback through CE, then a rally past the old highs.
    """
    t0 = datetime(2024, 3, 4, 20, 0, tzinfo=NY)
    w = 0.00010
    b = zigzag(t0, 5, 1.07000, [1.07600, 1.07300, 1.08200, 1.07900, 1.09000], 100, w)
    b += zigzag(b[-1].close_time, 5, 1.09000,
                [1.08600, 1.08700, 1.08400, 1.08650, 1.08100, 1.08300], 8, w)

    _append(b, 5, 1.08280, 1.08300, 1.07880, 1.08150)          # raid of 1.08100
    _append(b, 5, 1.08150, 1.08200, 1.08120, 1.08180)          # c1: gap lower edge 1.08200
    _append(b, 5, 1.08180, 1.09020, 1.08170, 1.09000)          # c2: displacement + MSS
    _append(b, 5, 1.09000, 1.09300, 1.08600, 1.09250)          # c3: gap [1.08200, 1.08600]
    for h in (1.09600, 1.09850, 1.10000):
        _append(b, 5, b[-1].close, h + 0.00020, b[-1].close - 0.00030, h)
    for c in (1.09600, 1.09100, 1.08700, 1.08400, 1.08330, 1.08340):
        p = b[-1].close
        _append(b, 5, p, max(p, c) + 0.00020, min(p, c) - 0.00020, c)
    for c in (1.08700, 1.09200, 1.09750, 1.10200, 1.10600, 1.11000, 1.11400):
        p = b[-1].close
        _append(b, 5, p, max(p, c) + 0.00020, min(p, c) - 0.00020, c)

    # --- daily: bearish sequence, a displacement that shifts structure, then bullish ---------
    d0 = t0 - timedelta(days=140)
    d = zigzag(d0, 1440, 1.09000,
               [1.08000, 1.08700, 1.07500, 1.08200, 1.06800, 1.07400, 1.06000], 3, 0.00050)
    _append(d, 1440, 1.06000, 1.08050, 1.05950, 1.08000)       # daily MSS above 1.07400
    d += zigzag(d[-1].close_time, 1440, 1.08000,
                [1.09000, 1.08500, 1.10000, 1.09500, 1.11000, 1.10500, 1.12000], 3, 0.00050)

    h4 = zigzag(t0 - timedelta(days=40), 240,
                1.05000, [1.06000, 1.05500, 1.07000, 1.06500, 1.08000, 1.07500, 1.09000],
                6, 0.00040)

    return MarketData(
        instrument="SYNTH",
        series={"1m": Series("1m", explode(b)),
                "3m": Series("3m", resample(explode(b), 3)),
                "5m": Series("5m", b),
                "15m": Series("15m", resample(b, 3)),
                "30m": Series("30m", resample(b, 6)),
                "1h": Series("1h", resample(b, 12)),
                "4h": Series("4h", h4),
                "1d": Series("1d", d),
                "1w": Series("1w", resample(d, 5)),
                "1M": Series("1M", resample(d, 21))},
    )


def with_correlated() -> MarketData:
    """The same scenario plus a second, strongly correlated instrument for the SMT variant."""
    primary = long_sweep_displacement_scenario()
    secondary = long_sweep_displacement_scenario()
    shifted = {}
    for tf, s in secondary.series.items():
        shifted[tf] = Series(tf, [Bar(x.open_time, x.close_time, x.open * 1.5 + 0.0001,
                                      x.high * 1.5 + 0.0001, x.low * 1.5 + 0.0001,
                                      x.close * 1.5 + 0.0001) for x in s.bars])
    primary.correlated["secondary"] = MarketData("SYNTH2", shifted)
    return primary


def resample(bars: List[Bar], group_size: int) -> List[Bar]:
    out, group = [], []
    for x in bars:
        group.append(x)
        if len(group) == group_size:
            out.append(_merge(group))
            group = []
    if group:
        out.append(_merge(group))
    return out


def _merge(group: List[Bar]) -> Bar:
    return Bar(group[0].open_time, group[-1].close_time, group[0].open,
               max(g.high for g in group), min(g.low for g in group), group[-1].close)


def explode(bars: List[Bar]) -> List[Bar]:
    """Five one-minute bars per five-minute bar, monotone from open to close."""
    out: List[Bar] = []
    for x in bars:
        for k in range(5):
            o = x.open + (x.close - x.open) * k / 5
            c = x.open + (x.close - x.open) * (k + 1) / 5
            hi = x.high if k == 2 else max(o, c)
            lo = x.low if k == 2 else min(o, c)
            t = x.open_time + timedelta(minutes=k)
            out.append(Bar(t, t + timedelta(minutes=1), o, hi, lo, c))
    return out
