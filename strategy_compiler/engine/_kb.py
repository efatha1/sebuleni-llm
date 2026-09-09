"""Loader for the knowledge-base reference primitives.

The primitive implementations are NOT duplicated here. `strategy_reearcher/engine/ict_primitives.py`
is the reference implementation derived from the knowledge base; re-implementing it would risk
altering trading logic. This module simply makes it importable from the compiler package.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_REF = (
    pathlib.Path(__file__).resolve().parents[2]
    / "strategy_reearcher"
    / "engine"
    / "ict_primitives.py"
)

if not _REF.exists():  # pragma: no cover - configuration error
    raise ImportError(f"reference primitive library not found at {_REF}")

_spec = importlib.util.spec_from_file_location("ict_primitives", _REF)
ict_primitives = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("ict_primitives", ict_primitives)
_spec.loader.exec_module(ict_primitives)

P = ict_primitives
UnspecifiedParameter = ict_primitives.UnspecifiedParameter
Candle = ict_primitives.Candle
NY = ict_primitives.NY
