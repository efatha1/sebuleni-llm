#!/usr/bin/env python3
"""Run a compiled strategy, or emit the configuration skeleton needed to run one.

    # what must be frozen before this strategy can run?
    python3 -m strategy_compiler.tools.run_backtest --describe S01-BUY-11STEP > cfg.json

    # run it
    python3 -m strategy_compiler.tools.run_backtest \
        --config cfg.json --data bars.json --out result.json

`--describe` produces a skeleton with every required value left as null. Nothing in this tool
supplies a default for a value the knowledge base does not specify: the engine refuses to start
until the skeleton is filled in, which is the freeze-before-testing discipline (ADV-M18-R02) made
mechanical.

Bar data format (`--data`), a JSON document:

    {
      "instrument": "EURUSD",
      "series": {
        "5m": [{"open_time": "2024-03-04T20:00:00-05:00",
                "close_time": "2024-03-04T20:05:00-05:00",
                "open": 1.07, "high": 1.071, "low": 1.069, "close": 1.0705}, ...],
        "1d": [...]
      },
      "correlated": {"secondary": {"instrument": "GBPUSD", "series": {...}}}
    }

Times must be ISO-8601 and timezone-aware: every session window is anchored to New York time
(BEG-M08-R05), so a naive timestamp is rejected rather than guessed at.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from strategy_compiler.engine import backtest as BT              # noqa: E402
from strategy_compiler.engine import dsl as DSL                  # noqa: E402
from strategy_compiler.engine.data import MarketData, bars_from_records   # noqa: E402
from strategy_compiler.engine.freeze import FrozenConfig         # noqa: E402
from strategy_compiler.tests import paths                        # noqa: E402

MANDATORY_STATEMENT = (
    "These results describe this operationalisation of the strategy specification, not ICT "
    "doctrine (ADV-M18-R01). Every value under 'frozen_config' whose knowledge-base status is "
    "unspecified, heuristic_unfixed, range_given or alternatives_documented is a research "
    "parameter chosen by the researcher, as is every entry under 'operationalisations' and the "
    "three execution-model fields (setup_expiry_bars, intrabar_policy, latch supersession)."
)


# ---------------------------------------------------------------------------
def load_market_data(path: str) -> MarketData:
    with open(path) as fh:
        raw = json.load(fh)
    series = {tf: bars_from_records(tf, recs) for tf, recs in raw["series"].items()}
    correlated = {}
    for name, sub in (raw.get("correlated") or {}).items():
        correlated[name] = MarketData(
            sub.get("instrument", name),
            {tf: bars_from_records(tf, recs) for tf, recs in sub["series"].items()},
        )
    return MarketData(raw.get("instrument", "unknown"), series, correlated)


def describe(strategy_id: str) -> dict:
    doc = DSL.load(os.path.join(paths.COMPILED, f"{strategy_id}.json"))
    params, help_ = {}, {}
    for p in sorted(doc["parameters"], key=lambda x: x["name"]):
        if p["binding"] == "literal":
            params[p["name"]] = p["value"]
        else:
            params[p["name"]] = None
        entry = {"binding": p["binding"], "kb_status": p["kb_status"],
                 "kb_value": p["kb_value"], "source": p["source"]}
        if p["binding"] == "frozen_choice":
            entry["choices"] = p["choices"]
        help_[p["name"]] = entry

    return {
        "_meta": {
            "generated_by": "strategy_compiler.tools.run_backtest --describe",
            "instructions": (
                "Fill every null, record date_frozen, and do not edit after results are seen "
                "(ADV-M18-R04: post-hoc changes are new research). Values are research "
                "parameters, never doctrine (ADV-M18-R01)."
            ),
            "strategy": doc["name"],
            "executability": doc["executability"],
            "specificity_status": doc["provenance"]["specificity_status"],
        },
        "strategy_id": strategy_id,
        "date_frozen": None,
        "instrument": {"symbol": None, "tick_size": None, "value_per_unit_move": None,
                       "spread": 0.0, "slippage": 0.0},
        "timeframe_roles": {r: None for r in doc["timeframes"]},
        "starting_equity": 100000.0,
        "intrabar_policy": "stop_first",
        "setup_expiry_bars": None,
        "params": params,
        "operationalisations": {i: None for i in doc["blocking_items"]},
        "_timeframe_help": {
            r: {"purpose": s["purpose"], "candidates": s["candidates"],
                "optional": bool(s.get("optional")), "min_history": s["min_history"]}
            for r, s in doc["timeframes"].items()
        },
        "_params_help": help_,
        "_blocking_items": [
            {"item_id": u["item_id"], "element": u["element"], "reason_code": u["reason_code"],
             "explanation": u["explanation"], "resolution": u["resolution"]}
            for u in doc["unsupported"] if u["blocks_execution"]
        ],
        "_execution_model_note": (
            "setup_expiry_bars and intrabar_policy are decided by no specification. They are "
            "execution-model research parameters and are recorded in the run manifest."
        ),
    }


def summarise(result: BT.Result) -> dict:
    """The reporting minimum from ADV-M18-R07, computed from realised R only.

    A trade still open when the sample ends is excluded from win rate and expectancy — its
    outcome is not known. Any R it has already banked on partials is reported separately rather
    than folded in, so the excluded amount is visible instead of silently missing.
    """
    rs = [t.r_total for t in result.trades if t.closed]
    open_r = sum(t.r_total for t in result.trades if not t.closed)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    peak = equity = drawdown = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return {
        "trades_total": len(result.trades),
        "trades_closed": len(rs),
        "trades_open_at_sample_end": len(result.trades) - len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / len(rs)) if rs else None,
        "avg_win_r": (sum(wins) / len(wins)) if wins else None,
        "avg_loss_r": (sum(losses) / len(losses)) if losses else None,
        "expectancy_r": (sum(rs) / len(rs)) if rs else None,
        "total_r": sum(rs),
        "max_drawdown_r": drawdown,
        "r_banked_on_still_open_trades": open_r,
        "note": ("Open trades are excluded from win rate and expectancy. Sample adequacy is the "
                 "researcher's responsibility: the capstone standard is 100 trading days / 50 "
                 "complete setups across multiple regimes (ADV-M19-S01)."),
    }


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--describe", metavar="STRATEGY_ID",
                    help="emit a frozen-configuration skeleton for one strategy")
    ap.add_argument("--list", action="store_true", help="list the compiled strategies")
    ap.add_argument("--config", help="a filled-in frozen configuration")
    ap.add_argument("--data", help="bar data JSON")
    ap.add_argument("--out", help="where to write the enriched result (default: stdout)")
    args = ap.parse_args()

    if args.list:
        for sid, doc in sorted(DSL.load_all(paths.COMPILED).items()):
            flag = "blocked " if doc["executability"] == "blocked" else "runnable"
            print(f"{flag}  {sid:<32} {doc['direction']:<24} {doc['name']}")
        return 0

    if args.describe:
        print(json.dumps(describe(args.describe), indent=2))
        return 0

    if not (args.config and args.data):
        ap.error("--config and --data are required unless --describe or --list is used")

    cfg = FrozenConfig.from_file(args.config)
    doc = DSL.load(os.path.join(paths.COMPILED, f"{cfg.strategy_id}.json"))
    result = BT.run(doc, load_market_data(args.data), cfg)

    payload = {
        "manifest": result.manifest,
        "diagnostics": result.diagnostics,
        "summary": summarise(result),
        "frozen_config": cfg.as_dict(),
        "trades": result.as_records(),
        "mandatory_statement": MANDATORY_STATEMENT,
    }
    text = json.dumps(payload, indent=2, sort_keys=False)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
        s = payload["summary"]
        expectancy = "n/a" if s["expectancy_r"] is None else f"{s['expectancy_r']:.3f}R"
        print(f"{cfg.strategy_id}: {s['trades_total']} trades "
              f"({s['trades_closed']} closed, {s['trades_open_at_sample_end']} open at sample "
              f"end), expectancy {expectancy}  -> {args.out}")
        print(f"trades_digest {result.manifest['trades_digest']}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
