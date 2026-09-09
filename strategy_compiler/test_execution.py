"""Executable behaviour of the compiled DSL, and the determinism contract."""
from __future__ import annotations

import copy
import json

from strategy_compiler.engine import backtest as BT
from strategy_compiler.engine import dsl as DSL
from strategy_compiler.engine.errors import MissingParameter, UnsupportedCondition
from strategy_compiler.engine.freeze import FrozenConfig
from strategy_compiler.tests import paths
from strategy_compiler.tests.synthetic import long_sweep_displacement_scenario


def _cfg() -> FrozenConfig:
    return FrozenConfig.from_file(paths.CONFIG_S01)


def _doc():
    return DSL.load(f"{paths.COMPILED}/S01-BUY-11STEP.json")


def test_compiled_strategy_executes_the_documented_sequence():
    res = BT.run(_doc(), long_sweep_displacement_scenario(), _cfg())
    assert len(res.trades) == 1, res.diagnostics
    t = res.trades[0]
    assert t.direction == "long"
    # Step 9: entry at the consequent encroachment of the London-created gap ([1.08200, 1.08600])
    assert abs(t.entry_price - 1.08400) < 1e-9
    # Step 10 stop: just beyond the low of the liquidity sweep, with the frozen buffer
    assert abs(t.stop_price - (t.bindings["sweep_extreme"] - 10 * 0.00001)) < 1e-12
    assert t.stop_price < 1.08200                      # below the far side of the entry array
    # the eleven-step chain latched in order
    order = [e["node_id"] for e in t.setup_events]
    assert order == ["S01.setup.03", "S01.setup.04", "S01.setup.05",
                     "S01.setup.06", "S01.setup.07", "S01.setup.08"]
    idx = [e["bar_index"] for e in t.setup_events]
    assert idx == sorted(idx)
    assert t.exits and t.exits[0].reason == "target_0"


def test_two_runs_agree_on_every_digest():
    doc, md = _doc(), long_sweep_displacement_scenario()
    a = BT.run(doc, md, _cfg())
    b = BT.run(_doc(), long_sweep_displacement_scenario(), _cfg())
    for k in ("dsl_digest", "config_digest", "instrument_digest", "data_digest", "trades_digest"):
        assert a.manifest[k] == b.manifest[k], k
    assert json.dumps(a.as_dict(), sort_keys=True) == json.dumps(b.as_dict(), sort_keys=True)


def test_parameter_insertion_order_does_not_change_the_result():
    doc, md = _doc(), long_sweep_displacement_scenario()
    a = BT.run(doc, md, _cfg())
    cfg = _cfg()
    cfg.params = dict(reversed(list(cfg.params.items())))
    b = BT.run(_doc(), long_sweep_displacement_scenario(), cfg)
    assert a.manifest["trades_digest"] == b.manifest["trades_digest"]
    assert a.manifest["config_digest"] == b.manifest["config_digest"]


def test_changing_one_frozen_parameter_changes_the_digest():
    doc, md = _doc(), long_sweep_displacement_scenario()
    a = BT.run(doc, md, _cfg())
    cfg = _cfg()
    cfg.params["stop_buffer_ticks"] = 25
    b = BT.run(_doc(), long_sweep_displacement_scenario(), cfg)
    assert a.manifest["config_digest"] != b.manifest["config_digest"]
    assert a.trades[0].stop_price != b.trades[0].stop_price


def test_missing_frozen_parameter_refuses_to_start():
    cfg = _cfg()
    del cfg.params["displacement_range_multiple"]
    try:
        BT.run(_doc(), long_sweep_displacement_scenario(), cfg)
        assert False, "expected MissingParameter before any bar was processed"
    except MissingParameter:
        pass


def test_off_menu_choice_refuses_to_start():
    cfg = _cfg()
    cfg.params["ote_levels"] = [0.5, 0.6, 0.7]
    try:
        BT.run(_doc(), long_sweep_displacement_scenario(), cfg)
        assert False, "expected MissingParameter"
    except MissingParameter:
        pass


def test_missing_execution_model_parameter_refuses_to_start():
    cfg = _cfg()
    cfg.setup_expiry_bars = None
    try:
        BT.run(_doc(), long_sweep_displacement_scenario(), cfg)
        assert False, "expected MissingParameter"
    except MissingParameter:
        pass


def test_blocked_strategies_refuse_to_run_without_a_recorded_operationalisation():
    docs = DSL.load_all(paths.COMPILED)
    blocked = [d for d in docs.values() if d["executability"] == "blocked"]
    assert len(blocked) >= 7
    for doc in blocked:
        cfg = _cfg()
        cfg.strategy_id = doc["strategy_id"]
        cfg.timeframe_roles = {r: doc["timeframes"][r]["candidates"][0]
                               for r in doc["timeframes"]}
        for p in doc["parameters"]:
            if p["binding"] == "frozen_choice":
                cfg.params[p["name"]] = next(c for c in p["choices"] if c is not None)
            elif p["binding"] == "frozen_required":
                cfg.params.setdefault(p["name"], 1)
        try:
            DSL.prepare(doc, cfg)
            assert False, f"{doc['strategy_id']} started without an operationalisation"
        except UnsupportedCondition:
            pass


def test_intrabar_policy_is_honoured():
    cfg_stop = _cfg()
    cfg_tgt = _cfg()
    cfg_tgt.intrabar_policy = "target_first"
    a = BT.run(_doc(), long_sweep_displacement_scenario(), cfg_stop)
    b = BT.run(_doc(), long_sweep_displacement_scenario(), cfg_tgt)
    assert a.manifest["intrabar_policy"] == "stop_first"
    assert b.manifest["intrabar_policy"] == "target_first"
    assert a.manifest["config_digest"] != b.manifest["config_digest"]
