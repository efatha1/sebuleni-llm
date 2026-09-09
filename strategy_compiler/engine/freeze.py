"""Frozen run configuration.

Mirrors `strategy_reearcher/research/research_config_template.json` and the discipline it
encodes (ADV-M18-R02: freeze before labelling; ADV-M18-R01: frozen values are research
parameters, never doctrine). There are no defaults anywhere in this module: a parameter the
knowledge base does not specify must be supplied by the caller or the run refuses to start.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import time
from typing import Any, Dict, List, Optional

from .data import digest
from .errors import MissingParameter, UnsupportedCondition


def parse_window(value) -> tuple:
    """['02:00','05:00'] -> (time(2,0), time(5,0))."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        out = []
        for v in value:
            if isinstance(v, time):
                out.append(v)
            else:
                hh, mm = str(v).split(":")
                out.append(time(int(hh), int(mm)))
        return tuple(out)
    raise MissingParameter(f"expected a two-element window, got {value!r}")


@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str
    tick_size: float
    value_per_unit_move: float      # account currency per 1.0 of price movement per unit of size
    spread: float = 0.0
    slippage: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tick_size": self.tick_size,
            "value_per_unit_move": self.value_per_unit_move,
            "spread": self.spread,
            "slippage": self.slippage,
        }


@dataclass
class FrozenConfig:
    """Values frozen before any label is produced."""

    strategy_id: str
    instrument: InstrumentConfig
    timeframe_roles: Dict[str, str]              # role -> timeframe identifier
    params: Dict[str, Any] = field(default_factory=dict)
    operationalisations: Dict[str, str] = field(default_factory=dict)
    starting_equity: float = 100_000.0
    intrabar_policy: str = "stop_first"
    setup_expiry_bars: Optional[int] = None
    date_frozen: Optional[str] = None
    notes: str = ""

    # -- parameter access -------------------------------------------------
    def require(self, name: str) -> Any:
        if name not in self.params or self.params[name] is None:
            raise MissingParameter(
                f"parameter '{name}' is not frozen. The knowledge base does not specify it; "
                f"supply it in the frozen configuration and report it as a research parameter "
                f"(ADV-M18-C03), never as doctrine (ADV-M18-R01)."
            )
        return self.params[name]

    def require_choice(self, name: str, choices: List[Any]) -> Any:
        v = self.require(name)
        norm = [_normalise(c) for c in choices]
        if _normalise(v) not in norm:
            raise MissingParameter(
                f"parameter '{name}' = {v!r} is outside the values the knowledge base documents "
                f"({choices!r}). Choosing outside them is outside the knowledge base."
            )
        return v

    def require_operationalisation(self, item_id: str) -> str:
        if item_id not in self.operationalisations:
            raise UnsupportedCondition(
                f"unsupported item '{item_id}' blocks execution and has no recorded "
                f"operationalisation. Add it to operationalisations{{}} before running; it will "
                f"be copied into the run manifest as a research operationalisation."
            )
        return self.operationalisations[item_id]

    def window(self, name: str) -> tuple:
        return parse_window(self.require(name))

    # -- reference-primitive bridge --------------------------------------
    def frozen_params(self):
        """Build the reference library's FrozenParams from whatever has been frozen here.

        Fields that were not frozen stay None, so the reference implementation keeps raising
        UnspecifiedParameter for them rather than silently substituting a value.
        """
        from ._kb import P

        def opt(name, conv=None):
            v = self.params.get(name)
            if v is None:
                return None
            return conv(v) if conv else v

        levels = self.params.get("ote_levels")
        if levels is not None:
            levels = tuple(levels)

        return P.FrozenParams(
            displacement_range_multiple=opt("displacement_range_multiple", float),
            displacement_lookback=opt("displacement_lookback", int),
            displacement_body_ratio_min=opt("displacement_body_ratio_min", float),
            equal_level_tolerance=opt("equal_level_tolerance", float),
            sweep_min_penetration=opt("sweep_min_penetration", float),
            sweep_reclaim_bars=opt("sweep_reclaim_bars", int),
            fib_anchor=opt("fib_anchor"),
            ote_levels=levels,
            london_open_kz=opt("london_open_kz_ET", parse_window),
            new_york_open_kz=opt("new_york_open_kz_ET", parse_window),
            asian_window=opt("asian_window_ET", parse_window),
            london_close_kz=opt("london_close_kz_ET", parse_window),
            risk_fraction=opt("risk_fraction", float),
        )

    # -- provenance -------------------------------------------------------
    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "instrument": self.instrument.as_dict(),
            "timeframe_roles": dict(sorted(self.timeframe_roles.items())),
            "params": {k: _normalise(v) for k, v in sorted(self.params.items())},
            "operationalisations": dict(sorted(self.operationalisations.items())),
            "starting_equity": self.starting_equity,
            "intrabar_policy": self.intrabar_policy,
            "setup_expiry_bars": self.setup_expiry_bars,
            "date_frozen": self.date_frozen,
        }

    def digest(self) -> str:
        return digest(self.as_dict())

    @staticmethod
    def from_file(path: str) -> "FrozenConfig":
        with open(path) as fh:
            raw = json.load(fh)
        return FrozenConfig.from_dict(raw)

    @staticmethod
    def from_dict(raw: Dict[str, Any]) -> "FrozenConfig":
        inst = raw["instrument"]
        return FrozenConfig(
            strategy_id=raw["strategy_id"],
            instrument=InstrumentConfig(
                symbol=inst["symbol"],
                tick_size=float(inst["tick_size"]),
                value_per_unit_move=float(inst["value_per_unit_move"]),
                spread=float(inst.get("spread", 0.0)),
                slippage=float(inst.get("slippage", 0.0)),
            ),
            timeframe_roles=dict(raw["timeframe_roles"]),
            params=dict(raw.get("params", {})),
            operationalisations=dict(raw.get("operationalisations", {})),
            starting_equity=float(raw.get("starting_equity", 100_000.0)),
            intrabar_policy=raw.get("intrabar_policy", "stop_first"),
            setup_expiry_bars=(int(raw["setup_expiry_bars"])
                               if raw.get("setup_expiry_bars") is not None else None),
            date_frozen=raw.get("date_frozen"),
            notes=raw.get("notes", ""),
        )


def _normalise(v):
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, (list, tuple)):
        return [_normalise(x) for x in v]
    return v
