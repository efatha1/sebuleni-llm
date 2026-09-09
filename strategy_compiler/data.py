"""Bar data, multi-timeframe containers and the look-ahead-controlled view.

The `View` is the single mechanism that enforces ADV-M18-R04: at a decision bar with close time
T, every timeframe is truncated to bars whose close_time <= T. No feature can see past T because
no feature receives anything other than a View.
"""
from __future__ import annotations

import bisect
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from ._kb import Candle
from .errors import MissingData

# Canonical timeframe identifiers, ordered from fastest to slowest. Used for the
# higher-timeframe-over-lower-timeframe priority rules (INT-M02-R03, ADV-M03-R03).
TIMEFRAME_ORDER = ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]


def tf_rank(tf: str) -> int:
    if tf not in TIMEFRAME_ORDER:
        raise MissingData(f"unknown timeframe identifier '{tf}'")
    return TIMEFRAME_ORDER.index(tf)


@dataclass(frozen=True)
class Bar:
    open_time: datetime          # tz-aware
    close_time: datetime         # tz-aware; the instant the bar becomes usable
    open: float
    high: float
    low: float
    close: float

    def candle(self) -> Candle:
        return Candle(self.open, self.high, self.low, self.close, self.close_time)


@dataclass
class Series:
    timeframe: str
    bars: List[Bar]

    def __post_init__(self):
        for i in range(1, len(self.bars)):
            if self.bars[i].close_time <= self.bars[i - 1].close_time:
                raise MissingData(
                    f"{self.timeframe}: bars must be strictly ordered by close_time "
                    f"(index {i} at {self.bars[i].close_time})"
                )
        for b in self.bars:
            if b.close_time.tzinfo is None or b.open_time.tzinfo is None:
                raise MissingData(f"{self.timeframe}: bar times must be timezone-aware")
        self._closes = [b.close_time for b in self.bars]

    def visible(self, cutoff: datetime) -> List[Bar]:
        """Bars whose close_time <= cutoff."""
        n = bisect.bisect_right(self._closes, cutoff)
        return self.bars[:n]


@dataclass
class MarketData:
    instrument: str
    series: Dict[str, Series]
    correlated: Dict[str, "MarketData"] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.correlated is None:
            self.correlated = {}

    def require(self, tf: str) -> Series:
        if tf not in self.series:
            raise MissingData(f"{self.instrument}: timeframe '{tf}' not supplied")
        return self.series[tf]

    def digest(self) -> str:
        h = hashlib.sha256()
        for tf in sorted(self.series):
            h.update(tf.encode())
            for b in self.series[tf].bars:
                h.update(
                    f"{b.open_time.astimezone(timezone.utc).isoformat()}|"
                    f"{b.close_time.astimezone(timezone.utc).isoformat()}|"
                    f"{b.open!r}|{b.high!r}|{b.low!r}|{b.close!r};".encode()
                )
        for name in sorted(self.correlated):
            h.update(f"~{name}~".encode())
            h.update(self.correlated[name].digest().encode())
        return h.hexdigest()


class View:
    """Immutable snapshot of every timeframe as of a decision bar's close time."""

    __slots__ = ("data", "cutoff", "_cache")

    def __init__(self, data: MarketData, cutoff: datetime):
        self.data = data
        self.cutoff = cutoff
        self._cache: Dict[str, List[Bar]] = {}

    def bars(self, tf: str) -> List[Bar]:
        cached = self._cache.get(tf)
        if cached is None:
            cached = self.data.require(tf).visible(self.cutoff)
            self._cache[tf] = cached
        return cached

    def candles(self, tf: str) -> List[Candle]:
        key = "~c~" + tf
        cached = self._cache.get(key)
        if cached is None:
            cached = [b.candle() for b in self.bars(tf)]
            self._cache[key] = cached  # type: ignore[assignment]
        return cached  # type: ignore[return-value]

    def correlated_view(self, name: str) -> "View":
        if name not in self.data.correlated:
            raise MissingData(f"correlated instrument '{name}' not supplied")
        return View(self.data.correlated[name], self.cutoff)


def bars_from_records(timeframe: str, records: Sequence[dict]) -> Series:
    """Build a Series from dicts with ISO-8601 'open_time'/'close_time' and OHLC floats."""
    out: List[Bar] = []
    for r in records:
        out.append(
            Bar(
                open_time=datetime.fromisoformat(r["open_time"]),
                close_time=datetime.fromisoformat(r["close_time"]),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
            )
        )
    return Series(timeframe, out)


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(obj) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()
