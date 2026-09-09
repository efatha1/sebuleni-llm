"""Every compiled strategy must load, prepare and run end to end without error.

Blocked strategies are run with their unsupported items explicitly operationalised, which is the
only way the engine permits them to execute, so the disclosure path is exercised too.
"""
from __future__ import annotations

from strategy_compiler.engine import backtest as BT
from strategy_compiler.engine import dsl as DSL
from strategy_compiler.engine.freeze import FrozenConfig, InstrumentConfig
from strategy_compiler.tests import paths
from strategy_compiler.tests.synthetic import with_correlated

NUMERIC = {
    "displacement_range_multiple": 2.0, "displacement_lookback": 3,
    "displacement_body_ratio_min": 0.6, "sweep_min_penetration": 0.0, "sweep_reclaim_bars": 3,
    "equal_level_tolerance": 0.0002, "risk_fraction": 0.01, "stop_buffer_ticks": 10,
    "first_target_allocation": 0.5, "decisive_close_min_ticks": 5, "reclaim_buffer": 0.0001,
    "max_daily_risk": 0.02, "daily_loss_limit": 0.03, "smt_correlation_min": 0.5,
    "smt_swing_comparison_window": 40,
}


def _config_for(doc) -> FrozenConfig:
    from strategy_compiler.engine.data import tf_rank

    roles = {}
    for role, spec in doc["timeframes"].items():
        roles[role] = min(spec["candidates"], key=tf_rank)
    cfg = FrozenConfig(
        strategy_id=doc["strategy_id"],
        instrument=InstrumentConfig("SYNTH", 0.00001, 100000.0),
        timeframe_roles=roles, params={}, setup_expiry_bars=60,
        date_frozen="2026-01-01",
    )
    for p in doc["parameters"]:
        if p["binding"] == "literal":
            cfg.params[p["name"]] = p["value"]
        elif p["binding"] == "frozen_choice":
            cfg.params[p["name"]] = next(c for c in p["choices"] if c is not None)
        else:
            cfg.params[p["name"]] = NUMERIC[p["name"]]
    for item in doc["blocking_items"]:
        cfg.operationalisations[item] = (
            "TEST OPERATIONALISATION — a smoke-test placeholder, not ICT doctrine (ADV-M18-R01)."
        )
    return cfg


def test_every_strategy_runs():
    md = with_correlated()
    ran = 0
    for sid, doc in sorted(DSL.load_all(paths.COMPILED).items()):
        if doc["blocks"]["entry"]["zone"] is None:
            continue                       # gate-only overlays have nothing to execute
        cfg = _config_for(doc)
        res = BT.run(doc, md, cfg)
        assert res.manifest["trades_digest"]
        assert res.diagnostics["bars"] > 0, sid
        ran += 1
    assert ran >= 22, ran


def test_overlay_documents_declare_what_they_gate():
    docs = DSL.load_all(paths.COMPILED)
    overlays = [d for d in docs.values() if d["blocks"]["entry"]["zone"] is None]
    for d in overlays:
        assert d["executability"] == "blocked"
        if "overlay_of" in d:
            for target in d["overlay_of"]:
                assert target in docs
