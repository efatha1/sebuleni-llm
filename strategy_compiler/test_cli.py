"""The command-line runner: configuration skeletons and end-to-end execution.

The round-trip test is the point of this module — it proves the skeleton `--describe` emits names
every value the engine will demand, so a researcher who fills it in can actually run.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

from strategy_compiler.engine import backtest as BT
from strategy_compiler.engine import dsl as DSL
from strategy_compiler.engine.freeze import FrozenConfig
from strategy_compiler.tests import paths
from strategy_compiler.tests.synthetic import long_sweep_displacement_scenario
from strategy_compiler.tools import run_backtest as CLI


def _dump_market_data(md, path):
    doc = {
        "instrument": md.instrument,
        "series": {
            tf: [{"open_time": b.open_time.isoformat(), "close_time": b.close_time.isoformat(),
                  "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                 for b in s.bars]
            for tf, s in md.series.items()
        },
    }
    with open(path, "w") as fh:
        json.dump(doc, fh)


def test_describe_names_every_value_the_engine_will_demand():
    for sid, doc in sorted(DSL.load_all(paths.COMPILED).items()):
        skeleton = CLI.describe(sid)
        assert skeleton["strategy_id"] == sid
        assert set(skeleton["timeframe_roles"]) == set(doc["timeframes"])
        assert set(skeleton["params"]) == {p["name"] for p in doc["parameters"]}
        assert set(skeleton["operationalisations"]) == set(doc["blocking_items"])
        # nothing the knowledge base leaves open may arrive pre-filled
        for p in doc["parameters"]:
            if p["binding"] == "literal":
                assert skeleton["params"][p["name"]] == p["value"]
            else:
                assert skeleton["params"][p["name"]] is None, p["name"]
        assert skeleton["setup_expiry_bars"] is None
        assert skeleton["instrument"]["tick_size"] is None


def test_describe_records_the_documented_choices():
    skeleton = CLI.describe("S01-BUY-11STEP")
    help_ = skeleton["_params_help"]
    assert help_["fib_anchor"]["choices"] == ["body", "wick"]
    assert help_["fib_anchor"]["kb_status"] == "alternatives_documented"
    assert help_["displacement_body_ratio_min"]["kb_status"] == "heuristic_unfixed"
    assert help_["displacement_body_ratio_min"]["source"]


def test_data_loader_round_trips_and_matches_the_in_process_run():
    md = long_sweep_displacement_scenario()
    cfg = FrozenConfig.from_file(paths.CONFIG_S01)
    doc = DSL.load(f"{paths.COMPILED}/S01-BUY-11STEP.json")
    expected = BT.run(doc, md, cfg)

    with tempfile.TemporaryDirectory() as tmp:
        data_path = os.path.join(tmp, "bars.json")
        _dump_market_data(md, data_path)
        loaded = CLI.load_market_data(data_path)
        assert loaded.digest() == md.digest()
        got = BT.run(doc, loaded, cfg)
        assert got.manifest["trades_digest"] == expected.manifest["trades_digest"]


def test_end_to_end_run_writes_the_enriched_result():
    md = long_sweep_displacement_scenario()
    expected = BT.run(DSL.load(f"{paths.COMPILED}/S01-BUY-11STEP.json"), md,
                      FrozenConfig.from_file(paths.CONFIG_S01))

    with tempfile.TemporaryDirectory() as tmp:
        data_path = os.path.join(tmp, "bars.json")
        out_path = os.path.join(tmp, "result.json")
        _dump_market_data(md, data_path)
        argv = sys.argv
        sys.argv = ["run_backtest", "--config", paths.CONFIG_S01,
                    "--data", data_path, "--out", out_path]
        try:
            assert CLI.main() == 0
        finally:
            sys.argv = argv
        payload = json.load(open(out_path))

    assert payload["manifest"]["trades_digest"] == expected.manifest["trades_digest"]
    assert set(payload) == {"manifest", "diagnostics", "summary", "frozen_config", "trades",
                            "mandatory_statement"}
    assert payload["trades"] == expected.as_records()
    assert "not ICT doctrine" in payload["mandatory_statement"]

    summary = payload["summary"]
    assert summary["trades_total"] == len(expected.trades)
    assert summary["trades_total"] >= 1
    # the runner in the synthetic scenario is still open when the sample ends
    assert summary["trades_closed"] + summary["trades_open_at_sample_end"] == summary["trades_total"]

    # the frozen configuration travels with the result so the run can be reproduced
    assert payload["frozen_config"]["strategy_id"] == "S01-BUY-11STEP"
    assert payload["frozen_config"]["setup_expiry_bars"] is not None


def test_summary_metrics_are_computed_from_realised_r():
    md = long_sweep_displacement_scenario()
    res = BT.run(DSL.load(f"{paths.COMPILED}/S01-BUY-11STEP.json"), md,
                 FrozenConfig.from_file(paths.CONFIG_S01))
    s = CLI.summarise(res)
    closed = [t.r_total for t in res.trades if t.closed]
    assert s["trades_closed"] == len(closed)
    assert abs(s["total_r"] - sum(closed)) < 1e-12
    if closed:
        assert abs(s["expectancy_r"] - sum(closed) / len(closed)) < 1e-12
        assert s["wins"] + s["losses"] <= s["trades_closed"]
    assert s["max_drawdown_r"] <= 0.0
