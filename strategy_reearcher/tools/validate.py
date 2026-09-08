#!/usr/bin/env python3
"""Validate the strategy research outputs against the knowledge base.

Checks:
  1. All output JSON files parse.
  2. Every knowledge-base object ID referenced anywhere in the outputs exists in the KB.
  3. Every P-* primitive referenced by a strategy exists in primitives.json.
  4. Every strategy has all required fields.
  5. Every parent_strategy_id / base_strategies reference resolves.
Usage: python3 validate.py <kb_repo_root> <outputs_dir>
"""
import glob
import json
import re
import sys

KB_ID = re.compile(r"\b(BEG|INT|ADV)-M\d\d-(C|R|S|EX|REL|NT|AMB|EMP)\d\d\b")
PRIM_ID = re.compile(r"\bP-[A-Z0-9]+-\d\d\b")
REQUIRED = [
    "strategy_id", "name", "source_concepts", "context", "prerequisites",
    "setup_sequence", "entry", "stop_invalidation", "target", "timeframe",
    "session", "direction", "parameters", "no_trade_conditions", "evidence_references",
]


def collect_kb_ids(root):
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

    for f in glob.glob(f"{root}/*/mod*.json"):
        walk(json.load(open(f)))
    return ids


def main(root, out):
    kb_ids = collect_kb_ids(root)
    files = ["primitives.json", "strategies.json", "comparison_tests.json",
             "concept_interactions.json", "parameter_register.json", "research_config_template.json"]
    data = {}
    for f in files:
        data[f] = json.load(open(f"{out}/{f}"))
    print(f"[ok] {len(files)} JSON files parse; KB has {len(kb_ids)} object ids")

    errors = 0
    for f in files:
        text = json.dumps(data[f])
        refs = set(KB_ID.findall(text) and [m.group(0) for m in KB_ID.finditer(text)])
        missing = sorted(r for r in refs if r not in kb_ids)
        print(f"[{'ok' if not missing else 'FAIL'}] {f}: {len(refs)} distinct KB refs, {len(missing)} missing")
        for m in missing:
            print("      missing:", m)
        errors += len(missing)

    # markdown / python refs
    for f in ["STRATEGY_CATALOG.md", "kb_numeric_audit.md", "ict_primitives.py", "test_primitives.py"]:
        text = open(f"{out}/{f}").read()
        refs = {m.group(0) for m in KB_ID.finditer(text)}
        missing = sorted(r for r in refs if r not in kb_ids)
        print(f"[{'ok' if not missing else 'FAIL'}] {f}: {len(refs)} distinct KB refs, {len(missing)} missing")
        for m in missing:
            print("      missing:", m)
        errors += len(missing)

    prims = {p["id"] for p in data["primitives.json"]["primitives"]}
    strat_text = json.dumps(data["strategies.json"])
    prim_refs = set(PRIM_ID.findall(strat_text))
    bad = sorted(p for p in prim_refs if p not in prims)
    print(f"[{'ok' if not bad else 'FAIL'}] strategies reference {len(prim_refs)} primitives; {len(bad)} unknown")
    errors += len(bad)

    strategies = data["strategies.json"]["strategies"]
    sids = {s["strategy_id"] for s in strategies}
    for s in strategies:
        miss = [k for k in REQUIRED if k not in s]
        if miss:
            print(f"[FAIL] {s['strategy_id']} missing fields: {miss}")
            errors += 1
        p = s.get("parent_strategy_id")
        if p and p not in sids:
            print(f"[FAIL] {s['strategy_id']} parent {p} not found")
            errors += 1
    print(f"[ok] {len(strategies)} strategies checked for required fields and parent links")

    for t in data["comparison_tests.json"]["tests"]:
        for b in t["base_strategies"]:
            if b not in sids:
                print(f"[FAIL] {t['test_id']} references unknown strategy {b}")
                errors += 1
    print(f"[ok] {len(data['comparison_tests.json']['tests'])} comparison tests checked")

    print("RESULT:", "PASS" if errors == 0 else f"FAIL ({errors} errors)")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
