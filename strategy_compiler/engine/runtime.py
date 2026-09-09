"""Expression evaluator and node semantics for the canonical Strategy DSL."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from . import features as F
from . import market_state as MS
from .errors import DSLValidationError
from .market_state import Ctx

OPS = {
    "const", "param", "binding", "feature", "state", "and", "or", "not",
    "==", "!=", "<", "<=", ">", ">=", "between", "in", "exists", "overlaps", "field", "if",
}


# ---------------------------------------------------------------------------
# market-state call surface (see requirements/market_state_requirements.json)
# ---------------------------------------------------------------------------
def _st_controlling_range(ctx: Ctx, tf: str):
    return MS.dealing_range(ctx, tf)


def _st_structure(ctx: Ctx, tf: str, upto_index: Optional[int] = None):
    return MS.structure(ctx, tf, upto_index)


def _st_swing_registry(ctx: Ctx, tf: str, side: str, tier: Optional[str] = None):
    return MS.swing_registry(ctx, tf, side, tier or MS._tier(ctx))


def _st_pool_registry(ctx: Ctx, tf: str, side: str, kinds: Sequence[str],
                      session_window_param: Optional[str] = None):
    return MS.pool_registry(ctx, tf, side, kinds, session_window_param)


def _st_array_registry(ctx: Ctx, tf: str, direction: str, since_index: int = 0):
    return MS.fvg_registry(ctx, tf, direction, since_index)


def _st_session_calendar(ctx: Ctx, window_param: str, tf: Optional[str] = None,
                         occurrence: int = 0):
    out = {"in_window": MS.in_session(ctx, window_param), "last_completed": None}
    if tf is not None:
        out["last_completed"] = MS.session_range(ctx, tf, window_param, occurrence)
    return out


def _st_period_opens(ctx: Ctx, period: str, tf: str = "execution"):
    return MS.period_open(ctx, period, tf)


def _st_bias_state(ctx: Ctx, tf: str, method: str = "structural", **kw):
    if method == "structural":
        return F.f_bias_structural(ctx, tf=tf, **kw)
    if method == "daily":
        return {"direction": F.f_bias_daily(ctx, tf=tf, **kw)}
    if method == "opening_price":
        return {"direction": F.f_bias_opening_price(ctx, **kw)}
    raise DSLValidationError(f"unknown bias method '{method}'")


def _st_po3_state(ctx: Ctx, tf: str, accumulation_window_param: str, period: str = "daily"):
    return {"phase": F.f_po3_phase(ctx, tf, accumulation_window_param, period)}


def _st_risk_state(ctx: Ctx):
    return {"equity": ctx.equity, "halted": bool(ctx.bindings.get("_risk_halted", False))}


def _st_correlated(ctx: Ctx, name: str):
    ctx.view.correlated_view(name)
    return name


STATE_REGISTRY = {
    "controlling_range": _st_controlling_range,
    "structure": _st_structure,
    "swing_registry": _st_swing_registry,
    "pool_registry": _st_pool_registry,
    "array_registry": _st_array_registry,
    "session_calendar": _st_session_calendar,
    "period_opens": _st_period_opens,
    "bias_state": _st_bias_state,
    "po3_state": _st_po3_state,
    "risk_state": _st_risk_state,
    "correlated_instrument_view": _st_correlated,
}


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------
def _is_expr(v) -> bool:
    return isinstance(v, list) and v and isinstance(v[0], str) and v[0] in OPS


def _kwargs(raw: Dict[str, Any], ctx: Ctx) -> Dict[str, Any]:
    return {k: (evaluate(v, ctx) if _is_expr(v) else v) for k, v in raw.items()}


def _apply_field(value, field: Optional[str]):
    if field is None or value is None:
        return value
    if isinstance(value, dict):
        return value.get(field)
    return getattr(value, field, None)


def evaluate(expr, ctx: Ctx):
    if not _is_expr(expr):
        raise DSLValidationError(f"not a DSL expression: {expr!r}")
    op = expr[0]

    if op == "const":
        return expr[1]
    if op == "param":
        return ctx.cfg.require(expr[1])
    if op == "binding":
        val = ctx.bindings.get(expr[1])
        return _apply_field(val, expr[2] if len(expr) > 2 else None)
    if op == "field":
        return _apply_field(evaluate(expr[1], ctx), expr[2])

    if op == "feature":
        name, raw = expr[1], (expr[2] if len(expr) > 2 else {})
        fn = F.REGISTRY.get(name)
        if fn is None:
            raise DSLValidationError(f"unknown feature '{name}'")
        kw = _kwargs(raw, ctx)
        field = kw.pop("field", None)
        return _apply_field(fn(ctx, **kw), field)

    if op == "state":
        name, raw = expr[1], (expr[2] if len(expr) > 2 else {})
        fn = STATE_REGISTRY.get(name)
        if fn is None:
            raise DSLValidationError(f"unknown market state '{name}'")
        kw = _kwargs(raw, ctx)
        field = kw.pop("field", None)
        return _apply_field(fn(ctx, **kw), field)

    if op == "if":
        return evaluate(expr[2], ctx) if bool(evaluate(expr[1], ctx)) else evaluate(expr[3], ctx)
    if op == "and":
        return all(bool(evaluate(a, ctx)) for a in expr[1:])
    if op == "or":
        return any(bool(evaluate(a, ctx)) for a in expr[1:])
    if op == "not":
        return not bool(evaluate(expr[1], ctx))
    if op == "exists":
        return evaluate(expr[1], ctx) is not None

    if op in ("==", "!=", "<", "<=", ">", ">="):
        a, b = evaluate(expr[1], ctx), evaluate(expr[2], ctx)
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if a is None or b is None:
            return False
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]

    if op == "between":
        x, lo, hi = (evaluate(e, ctx) for e in expr[1:4])
        if x is None or lo is None or hi is None:
            return False
        lo, hi = (lo, hi) if lo <= hi else (hi, lo)
        return lo <= x <= hi

    if op == "in":
        x = evaluate(expr[1], ctx)
        return x in evaluate(expr[2], ctx)

    if op == "overlaps":
        return F.f_zone_overlap(ctx, evaluate(expr[1], ctx), evaluate(expr[2], ctx)) is not None

    raise DSLValidationError(f"unknown operator '{op}'")


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------
def eval_node(node: Dict[str, Any], ctx: Ctx):
    """Evaluate a node's expression. Returns its value (bool for predicates/events)."""
    return evaluate(node["expr"], ctx)


def emit(node: Dict[str, Any], ctx: Ctx, value=None):
    """Publish this node's bindings. `emits` maps binding name -> expression; the literal
    expression ['const','$value'] refers to the node's own evaluated value."""
    for name, e in (node.get("emits") or {}).items():
        if e == ["const", "$value"]:
            ctx.bindings[name] = value
        else:
            ctx.bindings[name] = evaluate(e, ctx)
