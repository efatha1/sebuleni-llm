"""Translation fidelity: nothing added, nothing dropped, nothing paraphrased.

These are the tests that police the compilation mandate itself.
"""
from __future__ import annotations

import glob
import json
import os
import re

from strategy_compiler.engine import dsl as DSL
from strategy_compiler.tests import paths
from strategy_compiler.tools import compile_strategies as CS

KB_ID = re.compile(r"\b(BEG|INT|ADV)-M\d\d-(C|R|S|EX|REL|NT|AMB|EMP)\d\d\b")


def _kb_ids():
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


def test_every_specification_element_is_accounted_for():
    """Compiled, unsupported or unconstrained — exactly one of the three, for every element."""
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        cov = CS.coverage(doc)
        assert not cov["missing_elements"], f"{sid} dropped: {cov['missing_elements']}"
        assert not cov["unmatched_nodes"], f"{sid} invented: {cov['unmatched_nodes']}"


def test_source_text_is_verbatim():
    """A node's recorded source text must be byte-identical to the approved specification."""
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        cov = CS.coverage(doc)
        assert not cov["verbatim_errors"], f"{sid} paraphrased: {cov['verbatim_errors']}"


def test_all_knowledge_base_references_resolve():
    kb = _kb_ids()
    assert len(kb) > 500
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        refs = {m.group(0) for m in KB_ID.finditer(json.dumps(doc))}
        missing = sorted(r for r in refs if r not in kb)
        assert not missing, f"{sid} references non-existent knowledge-base objects: {missing}"


def test_only_catalogued_primitives_are_used():
    prims = {p["id"] for p in json.load(open(paths.PRIMITIVES))["primitives"]}
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        used = set(doc["provenance"]["primitives"])
        for _, n in DSL.iter_nodes(doc):
            used |= set(n["primitives"])
        unknown = sorted(p for p in used if p not in prims)
        assert not unknown, f"{sid} uses primitives outside the approved library: {unknown}"


def test_direction_matches_the_specification():
    spec = {s["strategy_id"]: s for s in json.load(open(paths.STRATEGIES))["strategies"]}
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        text = spec[sid]["direction"]
        if doc["direction"] == "long":
            assert text.startswith("long") and "or short" not in text, sid
        elif doc["direction"] == "short":
            assert text.startswith("short"), sid
        elif doc["direction"] == "reversal_bidirectional":
            assert text.startswith("reversal_bidirectional"), sid
        else:
            assert "long" in text and "short" in text, sid


def test_every_parameter_traces_to_the_parameter_register():
    known = {p["parameter"] for p in json.load(open(paths.PARAM_REGISTER))["parameters"]}
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        for p in doc["parameters"]:
            assert p["register_id"] in known, f"{sid}/{p['name']} -> {p['register_id']}"
            assert p["kb_status"] in {
                "specified", "specified_approx", "specified_examples", "range_given",
                "alternatives_documented", "heuristic_unfixed", "unspecified",
            }, f"{sid}/{p['name']}"


def test_no_trade_conditions_are_all_dispositioned():
    spec = {s["strategy_id"]: s for s in json.load(open(paths.STRATEGIES))["strategies"]}
    allowed = {"compiled", "enforced_by_sequence", "enforced_by_feature", "enforced_by_engine",
               "unsupported_process", "unsupported_subjective", "not_a_no_trade_object"}
    for sid, doc in DSL.load_all(paths.COMPILED).items():
        listed = spec[sid]["no_trade_conditions"]
        recorded = [d["kb_ref"] for d in doc["no_trade_dispositions"]]
        assert recorded == listed, f"{sid}: {recorded} != {listed}"
        for d in doc["no_trade_dispositions"]:
            assert d["disposition"] in allowed, f"{sid}: {d}"


def test_unsupported_items_are_well_formed_and_disclosed():
    reg = json.load(open(paths.UNSUPPORTED))
    assert reg["items"]
    seen = set()
    for u in reg["items"]:
        assert u["reason_code"] in DSL.REASON_CODES
        assert u["explanation"] and u["resolution"]
        if u["reason_code"] == "UNSUPPORTED_SUBJECTIVE" and not u["blocks_execution"]:
            assert "effect_if_unenforced" in u, u["item_id"]
        seen.add((u["strategy_id"], u["item_id"]))
    assert len(seen) == len(reg["items"]), "duplicate item ids within one strategy"


def test_recompilation_is_byte_stable():
    """Re-running the compiler must reproduce the checked-in documents exactly."""
    for sid in sorted(CS.SPEC):
        doc = CS.BUILDERS[sid]()
        on_disk = json.load(open(os.path.join(paths.COMPILED, f"{sid}.json")))
        assert doc == on_disk, f"{sid} differs from the checked-in compilation"
