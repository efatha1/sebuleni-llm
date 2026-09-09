"""Every compiled document loads, validates against the DSL schema, and is internally closed."""
from __future__ import annotations

import json
import os

from strategy_compiler.engine import dsl as DSL
from strategy_compiler.engine.features import REGISTRY as FEATURES
from strategy_compiler.engine.runtime import STATE_REGISTRY
from strategy_compiler.tests import paths

COMPILED = paths.COMPILED


def test_all_documents_load_and_validate():
    docs = DSL.load_all(COMPILED)
    assert len(docs) == 24, f"expected 24 compiled strategies, found {len(docs)}"
    for sid, doc in docs.items():
        DSL.validate(doc)
        assert doc["dsl_version"] == DSL.DSL_VERSION


def test_every_approved_specification_was_compiled():
    spec = {s["strategy_id"] for s in json.load(open(paths.STRATEGIES))["strategies"]}
    compiled = set(DSL.load_all(COMPILED))
    assert spec == compiled, f"missing={sorted(spec - compiled)} extra={sorted(compiled - spec)}"


def test_expressions_only_call_the_closed_feature_and_state_sets():
    registry = {f["feature_id"] for f in json.load(open(paths.FEATURE_REGISTRY))["features"]}
    registry |= {"bar", "latest_index", "offset", "midpoint", "pick"}   # data access / arithmetic
    states = {m["state_id"] for m in json.load(open(paths.MARKET_STATE))["market_state"]}
    for sid, doc in DSL.load_all(COMPILED).items():
        used = DSL.collect(doc)
        assert used["features"] <= set(FEATURES), sid
        assert used["features"] <= registry, f"{sid}: {sorted(used['features'] - registry)}"
        assert used["states"] <= set(STATE_REGISTRY), sid
        assert used["states"] <= states, f"{sid}: {sorted(used['states'] - states)}"


def test_every_node_is_traceable():
    for sid, doc in DSL.load_all(COMPILED).items():
        for block, n in DSL.iter_nodes(doc):
            assert n["kb_refs"], f"{sid}/{n['node_id']} has no knowledge-base reference"
            assert n["source"]["text"], f"{sid}/{n['node_id']} has no source text"
            assert n["primitives"], f"{sid}/{n['node_id']} names no primitive"


def test_blocked_strategies_declare_their_blockers():
    docs = DSL.load_all(COMPILED)
    blocked = {sid for sid, d in docs.items() if d["executability"] == "blocked"}
    assert blocked, "the registry claims blocking items exist, so some strategy must be blocked"
    for sid in blocked:
        doc = docs[sid]
        assert doc["blocking_items"]
        ids = {u["item_id"] for u in doc["unsupported"] if u["blocks_execution"]}
        assert ids == set(doc["blocking_items"])


def test_parameters_have_no_hidden_defaults():
    for sid, doc in DSL.load_all(COMPILED).items():
        for p in doc["parameters"]:
            if p["binding"] != "literal":
                assert "value" not in p, f"{sid}/{p['name']} carries a default value"
