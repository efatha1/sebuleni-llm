"""Deterministic backtest engine for the canonical Strategy DSL.

Execution model
---------------
* One clock: the execution timeframe (the fastest role bound in the configuration). All fills
  happen on that clock.
* One position at a time. A new setup is not tracked while a position is open, so trade order
  never depends on evaluation order.
* Setup events latch: an event's bar index is fixed when it first evaluates true and is never
  revised. Expiry windows are measured from the previously latched event.
* Context, prerequisite and no-trade gates are checked when a setup starts and re-checked at the
  entry bar (ADV-M16-R08), not on every intermediate bar.
* Intrabar ambiguity is resolved by `intrabar_policy` ('stop_first' or 'target_first'), never by
  data order.
* Management begins on the bar after entry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import dsl as DSL
from .data import MarketData, View, canonical_json, digest, tf_rank
from .errors import MissingParameter
from .freeze import FrozenConfig
from .market_state import Ctx, RiskState, _period_key
from .runtime import emit, evaluate


@dataclass
class Fill:
    bar_index: int
    time: str
    price: float
    allocation: float
    reason: str
    r_multiple: float


@dataclass
class Trade:
    strategy_id: str
    direction: str
    entry_index: int
    entry_time: str
    entry_price: float
    stop_price: float
    size: float
    targets: List[float] = field(default_factory=list)
    exits: List[Fill] = field(default_factory=list)
    setup_events: List[Dict[str, Any]] = field(default_factory=list)
    bindings: Dict[str, Any] = field(default_factory=dict)
    r_total: float = 0.0
    closed: bool = False

    def remaining(self) -> float:
        return 1.0 - sum(e.allocation for e in self.exits)


@dataclass
class Result:
    strategy_id: str
    trades: List[Trade]
    manifest: Dict[str, Any]
    diagnostics: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "trades": [asdict(t) for t in self.trades],
            "manifest": self.manifest,
            "diagnostics": self.diagnostics,
        }


def execution_role(doc: Dict[str, Any], cfg: FrozenConfig) -> str:
    bound = [r for r in doc["timeframes"] if r in cfg.timeframe_roles]
    if not bound:
        raise MissingParameter("no timeframe role is bound in the configuration")
    return min(bound, key=lambda r: (tf_rank(cfg.timeframe_roles[r]), r))


def run(doc: Dict[str, Any], data: MarketData, cfg: FrozenConfig) -> Result:
    DSL.validate(doc)
    DSL.prepare(doc, cfg)

    roles = dict(cfg.timeframe_roles)
    exec_role = execution_role(doc, cfg)
    exec_tf = roles[exec_role]
    roles.setdefault("execution", exec_tf)
    bars = data.require(exec_tf).bars
    warmup = int(doc["data_requirements"].get("warmup_bars", 50))

    blocks = doc["blocks"]
    setup_nodes = blocks["setup_sequence"]
    gates = list(blocks["context"]) + list(blocks["prerequisites"])
    no_trade = list(blocks["no_trade"])
    invalidation = list(blocks["invalidation"])
    entry_zone_node = blocks["entry"]["zone"]
    triggers = blocks["entry"]["triggers"]
    stop_node = blocks["stop"]
    target_nodes = blocks["targets"]

    trigger = _select_trigger(triggers, cfg)

    trades: List[Trade] = []
    risk = RiskState(equity=cfg.starting_equity)
    step = 0
    latched: List[Dict[str, Any]] = []
    bindings: Dict[str, Any] = {}
    open_trade: Optional[Trade] = None
    diagnostics = {"bars": 0, "setups_started": 0, "setups_completed": 0,
                   "setups_expired": 0, "setups_superseded": 0, "entries": 0,
                   "gate_rejections": 0}

    def new_ctx(i: int) -> Ctx:
        return Ctx(View(data, bars[i].close_time), cfg, roles, dict(bindings), risk.equity)

    def reset():
        nonlocal step, latched, bindings
        step, latched, bindings = 0, [], {}

    for i in range(warmup, len(bars)):
        bar = bars[i]
        diagnostics["bars"] += 1
        risk.roll(_period_key(bar.close_time, "daily"))

        if open_trade is not None:
            _manage(open_trade, bar, i, cfg, new_ctx(i), invalidation,
                    stop_node.get("execution_mode", "touch"))
            if open_trade.closed:
                pnl_r = open_trade.r_total
                risk.equity += pnl_r * cfg.require("risk_fraction") * risk.equity
                if pnl_r < 0:
                    risk.realised_loss_today += -pnl_r * cfg.require("risk_fraction") * risk.equity
                trades.append(open_trade)
                open_trade = None
                reset()
            continue

        if risk.halted(cfg):
            reset()
            continue

        ctx = new_ctx(i)
        if step == 0:
            if not _gate(ctx, gates, no_trade, allow_emit=True):
                continue
            bindings = dict(ctx.bindings)
        else:
            # Latch supersession: a pending setup is abandoned as soon as the market prints a
            # DIFFERENT first event (a different pool, or a different sweep of it). Without this
            # a latched liquidity event that never produced displacement would block the machine
            # for the rest of the sample. It is an execution-model rule, not a rule from the
            # source, and it is recorded in the run manifest.
            scratch = Ctx(View(data, bar.close_time), cfg, roles, {}, risk.equity)
            if _gate(scratch, gates, no_trade, allow_emit=True):
                first = setup_nodes[0]
                if bool(evaluate(first["expr"], scratch)):
                    emit(first, scratch, True)
                    keys = sorted(first.get("emits") or {})
                    now = canonical_json([scratch.bindings.get(k) for k in keys])
                    was = canonical_json([bindings.get(k) for k in keys])
                    if keys and now != was:
                        diagnostics["setups_superseded"] += 1
                        bindings = dict(scratch.bindings)
                        latched = [{"node_id": first["node_id"], "bar_index": i,
                                    "time": bar.close_time.isoformat()}]
                        step = 1
                        ctx = new_ctx(i)

        expired = False
        while step < len(setup_nodes):
            snode = setup_nodes[step]
            window = _within_bars(snode, cfg)
            if latched and window is not None and (i - latched[-1]["bar_index"]) > window:
                diagnostics["setups_expired"] += 1
                reset()
                ctx = new_ctx(i)
                if not _gate(ctx, gates, no_trade, allow_emit=True):
                    expired = True
                    break
                bindings = dict(ctx.bindings)
                continue
            if not bool(evaluate(snode["expr"], ctx)):
                break
            emit(snode, ctx, True)
            bindings = dict(ctx.bindings)
            latched.append({"node_id": snode["node_id"], "bar_index": i,
                            "time": bar.close_time.isoformat()})
            if step == 0:
                diagnostics["setups_started"] += 1
            step += 1
        if expired or step < len(setup_nodes):
            continue

        diagnostics["setups_completed"] += 1
        ctx = new_ctx(i)
        if not _gate(ctx, gates, no_trade, allow_emit=False):
            diagnostics["gate_rejections"] += 1
            reset()
            continue

        zone = evaluate(entry_zone_node["expr"], ctx)
        if zone is None:
            reset()
            continue
        emit(entry_zone_node, ctx, zone)
        ctx.bindings["entry_zone"] = zone
        bindings = dict(ctx.bindings)

        opened = _try_entry(doc, ctx, trigger, stop_node, target_nodes, blocks["risk"],
                            bar, i, cfg, risk)
        if opened is not None:
            opened.setup_events = list(latched)
            open_trade = opened
            diagnostics["entries"] += 1
            risk.risk_committed_today += cfg.require("risk_fraction") * risk.equity

    if open_trade is not None:                       # unresolved at the end of the sample
        trades.append(open_trade)

    manifest = {
        "dsl_digest": DSL.doc_digest(doc),
        "config_digest": cfg.digest(),
        "instrument_digest": digest(cfg.instrument.as_dict()),
        "data_digest": data.digest(),
        "engine_version": "1.0.0",
        "execution_timeframe": exec_tf,
        "intrabar_policy": cfg.intrabar_policy,
    }
    manifest["trades_digest"] = digest([asdict(t) for t in trades])
    return Result(doc["strategy_id"], trades, manifest, diagnostics)


# ---------------------------------------------------------------------------
def _select_trigger(triggers: List[Dict[str, Any]], cfg: FrozenConfig) -> Dict[str, Any]:
    if len(triggers) == 1:
        return triggers[0]
    choice = cfg.require_choice("entry_trigger", [t["trigger_id"] for t in triggers])
    for t in triggers:
        if t["trigger_id"] == choice:
            return t
    raise MissingParameter(f"entry trigger '{choice}' not found")


def _within_bars(node: Dict[str, Any], cfg: FrozenConfig) -> Optional[int]:
    o = node.get("ordering") or {}
    w = o.get("within_bars")
    if w is None:
        return cfg.setup_expiry_bars
    if isinstance(w, dict) and "param" in w:
        return int(cfg.require(w["param"]))
    return int(w)


def _gate(ctx: Ctx, gates, no_trade, allow_emit: bool = True) -> bool:
    """Context and prerequisite gates plus no-trade conditions.

    Nodes carrying "gate": false are evaluated for their bindings/diagnostics but do not veto:
    the specification states them as quality preferences ("stronger when ..."), not requirements,
    and promoting a preference to a filter would change the trading logic.
    """
    for n in gates:
        value = evaluate(n["expr"], ctx)
        if n.get("gate", True) and not bool(value):
            return False
        if allow_emit:
            emit(n, ctx, value)
    for n in no_trade:
        if bool(evaluate(n["expr"], ctx)):
            return False
    return True


def _try_entry(doc, ctx: Ctx, trigger, stop_node, target_nodes, risk_nodes,
               bar, i, cfg: FrozenConfig, risk: RiskState) -> Optional[Trade]:
    if not bool(evaluate(trigger["expr"], ctx)):
        return None
    fill = trigger["fill"]
    inst = cfg.instrument
    direction = doc["direction"]
    if direction in ("reversal_bidirectional", "either"):
        direction = ctx.bindings.get("trade_direction")
        if direction not in ("long", "short"):
            return None

    if fill["mode"] == "limit":
        price = evaluate(fill["price"], ctx)
        if price is None or not (bar.low <= price <= bar.high):
            return None
        entry = price + (inst.slippage if direction == "long" else -inst.slippage)
    elif fill["mode"] == "market_on_close":
        half = inst.spread / 2.0
        entry = bar.close + (half + inst.slippage if direction == "long" else -(half + inst.slippage))
    else:
        raise MissingParameter(f"unknown fill mode '{fill['mode']}'")

    ctx.bindings["entry_price"] = entry
    stop = evaluate(stop_node["expr"], ctx)
    if stop is None:
        return None
    if direction == "long" and stop >= entry:
        return None
    if direction == "short" and stop <= entry:
        return None
    ctx.bindings["stop_price"] = stop

    targets: List[float] = []
    allocations: List[float] = []
    for tn in target_nodes:
        v = evaluate(tn["expr"], ctx)
        if v is None:
            continue
        alloc = tn.get("allocation", 1.0)
        if isinstance(alloc, dict) and "param" in alloc:
            alloc = float(cfg.require(alloc["param"]))
        targets.append(float(v))
        allocations.append(float(alloc))
    if not targets:
        return None
    if sum(allocations) > 1.0 + 1e-9:
        raise MissingParameter("target allocations exceed 1.0")
    if sum(allocations) < 1.0:
        allocations[-1] += 1.0 - sum(allocations)      # runner carries the remainder

    rr_min = cfg.params.get("rr_minimum")
    if rr_min not in (None, "none"):
        first_r = abs(targets[0] - entry) / abs(entry - stop)
        if first_r < float(rr_min):
            return None

    for n in risk_nodes:
        emit(n, ctx, evaluate(n["expr"], ctx))

    size = ctx.bindings.get("position_size")
    if size is None:
        from .features import f_position_size

        size = f_position_size(ctx, entry, stop)

    t = Trade(
        strategy_id=doc["strategy_id"], direction=direction, entry_index=i,
        entry_time=bar.close_time.isoformat(), entry_price=entry, stop_price=stop,
        size=float(size), targets=targets,
    )
    t.bindings = {k: v for k, v in sorted(ctx.bindings.items())
                  if isinstance(v, (int, float, str, bool, type(None)))}
    t._allocations = allocations          # type: ignore[attr-defined]
    return t


def _r(trade: Trade, price: float) -> float:
    risk_dist = abs(trade.entry_price - trade.stop_price)
    if trade.direction == "long":
        return (price - trade.entry_price) / risk_dist
    return (trade.entry_price - price) / risk_dist


def _close(trade: Trade, i: int, bar, price: float, alloc: float, reason: str):
    trade.exits.append(
        Fill(i, bar.close_time.isoformat(), price, alloc, reason, _r(trade, price))
    )
    trade.r_total = sum(e.allocation * e.r_multiple for e in trade.exits)
    if trade.remaining() <= 1e-9:
        trade.closed = True


def _manage(trade: Trade, bar, i: int, cfg: FrozenConfig, ctx: Ctx, invalidation,
            stop_mode: str = "touch") -> None:
    if i <= trade.entry_index:
        return
    allocations: List[float] = getattr(trade, "_allocations")
    long = trade.direction == "long"

    def hit_stop() -> bool:
        if stop_mode == "close":
            # The specification words this invalidation as a *decisive close* beyond the
            # reference, not as a touch (INT-M06-S01, ADV-M11-S01). The 'decisive' magnitude is
            # the frozen decisive_close_definition, so the same test is reused here.
            from .features import _decisive_beyond

            return _decisive_beyond(ctx, bar, trade.stop_price, "below" if long else "above")
        return bar.low <= trade.stop_price if long else bar.high >= trade.stop_price

    def take_targets():
        for k, tgt in enumerate(trade.targets):
            if k < len(trade.exits) and trade.exits[k].reason.startswith("target"):
                continue
            if any(e.reason == f"target_{k}" for e in trade.exits):
                continue
            reached = bar.high >= tgt if long else bar.low <= tgt
            if reached and not trade.closed:
                _close(trade, i, bar, tgt, allocations[k], f"target_{k}")

    if cfg.intrabar_policy == "stop_first":
        if hit_stop():
            price = bar.close if stop_mode == "close" else trade.stop_price
            _close(trade, i, bar, price, trade.remaining(), "stop")
            return
        take_targets()
    else:
        take_targets()
        if not trade.closed and hit_stop():
            price = bar.close if stop_mode == "close" else trade.stop_price
            _close(trade, i, bar, price, trade.remaining(), "stop")
            return

    if not trade.closed:
        for n in invalidation:
            if bool(evaluate(n["expr"], ctx)):
                _close(trade, i, bar, bar.close, trade.remaining(), f"invalidation:{n['node_id']}")
                break
