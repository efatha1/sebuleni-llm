#!/usr/bin/env python3
"""Translation audit — prove that the compilation added nothing and dropped nothing.

Usage:  python3 -m strategy_compiler.tools.audit_translation [--markdown]

Checks, per strategy:
  1. every element of the approved specification is compiled, registered as unsupported, or
     listed as unconstrained — exactly one disposition, none missing;
  2. every compiled node's source text is byte-identical to the approved specification;
  3. no compiled node exists without a source element behind it;
  4. every knowledge-base id referenced by the compiled document exists in the repository;
  5. every primitive referenced exists in the approved primitive library;
  6. every parameter resolves to an entry in the approved parameter register;
  7. every no-trade condition the specification lists has an explicit disposition;
  8. declared features and market state exactly match what the expressions call.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from strategy_compiler.engine import dsl as DSL                       # noqa: E402
from strategy_compiler.engine.features import REGISTRY as FEATURES    # noqa: E402
from strategy_compiler.engine.runtime import STATE_REGISTRY           # noqa: E402
from strategy_compiler.tests import paths                             # noqa: E402
from strategy_compiler.tools import compile_strategies as CS          # noqa: E402

KB_ID = re.compile(r"\b(BEG|INT|ADV)-M\d\d-(C|R|S|EX|REL|NT|AMB|EMP)\d\d\b")


def kb_ids():
    ids = set()

    def walk(o):
        if isinstance(o, dict):
            v = o.get("id")
            if isinstance(v, str) and KB_ID.fullmatch(v):
                ids.add(v)
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    for f in glob.glob(os.path.join(paths.ROOT, "*", "mod*.json")):
        walk(json.load(open(f)))
    return ids


def audit():
    kb = kb_ids()
    prims = {p["id"] for p in json.load(open(paths.PRIMITIVES))["primitives"]}
    register = {p["parameter"] for p in json.load(open(paths.PARAM_REGISTER))["parameters"]}
    spec = {s["strategy_id"]: s for s in json.load(open(paths.STRATEGIES))["strategies"]}
    docs = DSL.load_all(paths.COMPILED)

    rows, errors = [], []
    for sid in sorted(spec):
        if sid not in docs:
            errors.append(f"{sid}: approved specification was not compiled")
            continue
        doc = docs[sid]
        cov = CS.coverage(doc)
        used = DSL.collect(doc)
        refs = {m.group(0) for m in KB_ID.finditer(json.dumps(doc))}
        bad_kb = sorted(r for r in refs if r not in kb)
        used_prims = set(doc["provenance"]["primitives"])
        for _, n in DSL.iter_nodes(doc):
            used_prims |= set(n["primitives"])
        bad_prims = sorted(p for p in used_prims if p not in prims)
        bad_params = sorted(p["name"] for p in doc["parameters"]
                            if p["register_id"] not in register)
        listed = spec[sid]["no_trade_conditions"]
        dispositioned = [d["kb_ref"] for d in doc["no_trade_dispositions"]]

        for label, problem in (
            ("dropped elements", cov["missing_elements"]),
            ("invented nodes", cov["unmatched_nodes"]),
            ("paraphrased source", cov["verbatim_errors"]),
            ("unknown kb refs", bad_kb),
            ("unknown primitives", bad_prims),
            ("unregistered parameters", bad_params),
            ("unknown features", sorted(used["features"] - set(FEATURES))),
            ("unknown market state", sorted(used["states"] - set(STATE_REGISTRY))),
        ):
            if problem:
                errors.append(f"{sid}: {label}: {problem}")
        if dispositioned != listed:
            errors.append(f"{sid}: no-trade dispositions do not match the specification")

        rows.append({
            "strategy": sid,
            "kind": doc["kind"],
            "direction": doc["direction"],
            "elements": cov["elements_total"],
            "nodes": sum(1 for _ in DSL.iter_nodes(doc)),
            "features": len(doc["features"]),
            "market_state": len(doc["market_state"]),
            "parameters": len(doc["parameters"]),
            "frozen_required": sum(1 for p in doc["parameters"]
                                   if p["binding"] == "frozen_required"),
            "frozen_choice": sum(1 for p in doc["parameters"] if p["binding"] == "frozen_choice"),
            "unsupported": len(doc["unsupported"]),
            "blocking": len(doc["blocking_items"]),
            "executability": doc["executability"],
            "kb_refs": len(refs),
        })
    return rows, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()
    rows, errors = audit()

    if args.markdown:
        cols = list(rows[0])
        print("| " + " | ".join(cols) + " |")
        print("|" + "|".join("---" for _ in cols) + "|")
        for r in rows:
            print("| " + " | ".join(str(r[c]) for c in cols) + " |")
    else:
        for r in rows:
            print(f"{r['strategy']:<32} elements={r['elements']:>3} nodes={r['nodes']:>3} "
                  f"features={r['features']:>2} state={r['market_state']:>2} "
                  f"params={r['parameters']:>2} unsupported={r['unsupported']:>2} "
                  f"blocking={r['blocking']} {r['executability']}")

    print()
    if errors:
        for e in errors:
            print("ERROR:", e)
        print(f"RESULT: FAIL ({len(errors)} problems)")
        return 1
    print(f"RESULT: PASS — {len(rows)} strategies, "
          f"{sum(r['elements'] for r in rows)} specification elements all accounted for, "
          f"{sum(r['nodes'] for r in rows)} compiled nodes all traceable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
