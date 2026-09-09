"""Load, validate and prepare compiled Strategy DSL documents."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Set, Tuple

from . import features as F
from .data import digest
from .errors import DSLValidationError, MissingParameter, UnsupportedCondition
from .freeze import FrozenConfig
from .runtime import OPS, STATE_REGISTRY

DSL_VERSION = "1.0.0"

TF_KWARGS = ("tf", "price_tf", "range_tf")
PARAM_KWARGS = ("window_param", "accumulation_window_param", "session_window_param")

REQUIRED_TOP = [
    "dsl_version", "strategy_id", "name", "kind", "direction", "provenance",
    "timeframes", "data_requirements", "parameters", "features", "market_state",
    "blocks", "unsupported", "unconstrained", "executability",
]
BLOCK_KEYS = [
    "context", "prerequisites", "setup_sequence", "entry", "stop", "targets",
    "invalidation", "no_trade", "risk",
]
REASON_CODES = {
    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
    "UNSUPPORTED_SUBJECTIVE",
    "UNSUPPORTED_PROCESS",
    "UNSUPPORTED_EXTERNAL_DATA",
}


def load(path: str) -> Dict[str, Any]:
    with open(path) as fh:
        doc = json.load(fh)
    validate(doc)
    return doc


def load_all(directory: str) -> Dict[str, Dict[str, Any]]:
    out = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            doc = load(os.path.join(directory, name))
            out[doc["strategy_id"]] = doc
    return out


def iter_nodes(doc: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    b = doc["blocks"]
    for key in ("context", "prerequisites", "setup_sequence", "invalidation", "no_trade", "risk", "targets"):
        for n in b.get(key) or []:
            yield key, n
    entry = b.get("entry") or {}
    if entry.get("zone"):
        yield "entry.zone", entry["zone"]
    for n in entry.get("triggers") or []:
        yield "entry.trigger", n
    if b.get("stop"):
        yield "stop", b["stop"]


def walk_expr(expr, fn):
    if isinstance(expr, list) and expr and isinstance(expr[0], str) and expr[0] in OPS:
        fn(expr)
        for sub in expr[1:]:
            walk_expr(sub, fn)
        if expr[0] in ("feature", "state") and len(expr) > 2 and isinstance(expr[2], dict):
            for v in expr[2].values():
                walk_expr(v, fn)


def collect(doc: Dict[str, Any]) -> Dict[str, Set[str]]:
    used = {"features": set(), "states": set(), "params": set(), "roles": set(), "bindings": set()}

    def visit(e):
        op = e[0]
        if op == "feature":
            used["features"].add(e[1])
        elif op == "state":
            used["states"].add(e[1])
        elif op == "param":
            used["params"].add(e[1])
        elif op == "binding":
            used["bindings"].add(e[1])
        if op in ("feature", "state") and len(e) > 2 and isinstance(e[2], dict):
            for k, v in e[2].items():
                if k in TF_KWARGS and isinstance(v, str):
                    used["roles"].add(v)
                if k in PARAM_KWARGS and isinstance(v, str):
                    used["params"].add(v)

    for _, node in iter_nodes(doc):
        walk_expr(node.get("expr"), visit)
        for e in (node.get("emits") or {}).values():
            walk_expr(e, visit)
        fill = node.get("fill") or {}
        if "price" in fill:
            walk_expr(fill["price"], visit)
    return used


def validate(doc: Dict[str, Any]) -> None:
    sid = doc.get("strategy_id", "<unknown>")

    def bad(msg):
        raise DSLValidationError(f"{sid}: {msg}")

    for k in REQUIRED_TOP:
        if k not in doc:
            bad(f"missing top-level field '{k}'")
    if doc["dsl_version"] != DSL_VERSION:
        bad(f"dsl_version {doc['dsl_version']} != {DSL_VERSION}")
    for k in BLOCK_KEYS:
        if k not in doc["blocks"]:
            bad(f"missing block '{k}'")

    ids = [n["node_id"] for _, n in iter_nodes(doc)]
    if len(ids) != len(set(ids)):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        bad(f"duplicate node_id(s): {dupes}")
    for block, n in iter_nodes(doc):
        for k in ("node_id", "kind", "source", "kb_refs", "expr"):
            if k not in n:
                bad(f"node in '{block}' missing '{k}'")
        if n["kind"] not in ("predicate", "event", "selection", "action"):
            bad(f"{n['node_id']}: bad node kind '{n['kind']}'")
        for k in ("block", "index", "text"):
            if k not in n["source"]:
                bad(f"{n['node_id']}: source missing '{k}'")
        if not n["kb_refs"]:
            bad(f"{n['node_id']}: no kb_refs — every node must be traceable")

    params = {p["name"]: p for p in doc["parameters"]}
    for name, p in params.items():
        if p["binding"] not in ("literal", "frozen_required", "frozen_choice"):
            bad(f"parameter '{name}': bad binding '{p['binding']}'")
        if p["binding"] == "literal" and "value" not in p:
            bad(f"parameter '{name}': literal without value")
        if p["binding"] == "frozen_choice" and not p.get("choices"):
            bad(f"parameter '{name}': frozen_choice without choices")
        if not p.get("source"):
            bad(f"parameter '{name}': no source")

    used = collect(doc)
    for f in sorted(used["features"]):
        if f not in F.REGISTRY:
            bad(f"unknown feature '{f}'")
    for s in sorted(used["states"]):
        if s not in STATE_REGISTRY:
            bad(f"unknown market state '{s}'")
    for p in sorted(used["params"]):
        if p not in params:
            bad(f"expression references undeclared parameter '{p}'")
    for r in sorted(used["roles"]):
        if r not in doc["timeframes"]:
            bad(f"expression references undeclared timeframe role '{r}'")

    declared_f = set(doc["features"])
    if declared_f != used["features"]:
        bad(
            "declared features do not match used features: "
            f"missing={sorted(used['features'] - declared_f)} "
            f"extra={sorted(declared_f - used['features'])}"
        )
    declared_s = set(doc["market_state"])
    if declared_s != used["states"]:
        bad(
            "declared market_state does not match used market state: "
            f"missing={sorted(used['states'] - declared_s)} "
            f"extra={sorted(declared_s - used['states'])}"
        )

    for u in doc["unconstrained"]:
        for k in ("source", "note"):
            if k not in u:
                bad(f"unconstrained entry missing '{k}'")

    entry = doc["blocks"]["entry"]
    if entry.get("zone") is None or not entry.get("triggers"):
        if not any(u["blocks_execution"] for u in doc["unsupported"]):
            bad("entry zone/trigger absent without a blocking unsupported item")
    if doc["blocks"].get("stop") is None:
        if not any(u["blocks_execution"] for u in doc["unsupported"]):
            bad("stop absent without a blocking unsupported item")

    blocking = []
    for u in doc["unsupported"]:
        for k in ("item_id", "source", "element", "reason_code", "explanation", "kb_refs",
                  "blocks_execution", "resolution"):
            if k not in u:
                bad(f"unsupported item missing '{k}'")
        if u["reason_code"] not in REASON_CODES:
            bad(f"{u['item_id']}: unknown reason_code '{u['reason_code']}'")
        if u["blocks_execution"]:
            blocking.append(u["item_id"])
    expect = "blocked" if blocking else "executable"
    if doc["executability"] != expect:
        bad(f"executability '{doc['executability']}' but blocking items {blocking}")
    if sorted(doc.get("blocking_items", [])) != sorted(blocking):
        bad(f"blocking_items {doc.get('blocking_items')} != {sorted(blocking)}")


def prepare(doc: Dict[str, Any], cfg: FrozenConfig) -> None:
    """Fail fast, before any bar is processed, if the run is not fully frozen."""
    if cfg.strategy_id != doc["strategy_id"]:
        raise MissingParameter(
            f"configuration is for {cfg.strategy_id}, DSL is {doc['strategy_id']}"
        )
    for role in doc["timeframes"]:
        if doc["timeframes"][role].get("optional"):
            continue
        if role not in cfg.timeframe_roles:
            raise MissingParameter(f"timeframe role '{role}' is not bound in the configuration")
    for p in doc["parameters"]:
        if p["binding"] == "literal":
            cfg.params.setdefault(p["name"], p["value"])
        elif p["binding"] == "frozen_choice":
            cfg.require_choice(p["name"], p["choices"])
        else:
            cfg.require(p["name"])
    if cfg.setup_expiry_bars is None and not any(
        (n.get("ordering") or {}).get("within_bars") for n in doc["blocks"]["setup_sequence"]
    ):
        raise MissingParameter(
            "setup_expiry_bars is not set. The specification gives no lifetime for a "
            "partially-formed setup, so the execution model needs one: without it a latched "
            "liquidity event would wait forever. It is an execution-model research parameter "
            "(ADV-M18-C03), not a rule from the source, and it is recorded in the run manifest."
        )
    for item_id in doc.get("blocking_items", []):
        cfg.require_operationalisation(item_id)


def doc_digest(doc: Dict[str, Any]) -> str:
    return digest(doc)
