#!/usr/bin/env python3
"""Compile the approved strategy specifications into the canonical Strategy DSL.

Input   : strategy_reearcher/catalog/strategies.json   (approved specifications)
          strategy_reearcher/catalog/primitives.json   (primitive library)
          the knowledge-base module files              (no-trade statements)
Output  : strategy_compiler/dsl/compiled/<STRATEGY_ID>.json
          strategy_compiler/dsl/unsupported_registry.json
          strategy_compiler/requirements/timeframe_requirements.json

Translation discipline
----------------------
* Every node's `source.text` is copied verbatim from the approved specification. It is never
  paraphrased here, so the audit in tools/audit_translation.py can compare byte for byte.
* No node exists without a source element behind it, and no source element is dropped: it is
  either compiled, registered as unsupported, or listed as unconstrained.
* Where the source documents two alternatives, both are compiled behind a frozen_choice
  parameter and an ["if", ...] selector. Neither is preferred here.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))                 # sebuleni-llm
PKG = os.path.dirname(HERE)                                   # strategy_compiler
CATALOG = os.path.join(ROOT, "strategy_reearcher", "catalog")
OUT_DSL = os.path.join(PKG, "dsl", "compiled")
sys.path.insert(0, os.path.dirname(PKG))

SPEC = {s["strategy_id"]: s for s in json.load(open(os.path.join(CATALOG, "strategies.json")))["strategies"]}
PRIMS = {p["id"]: p for p in json.load(open(os.path.join(CATALOG, "primitives.json")))["primitives"]}


def _kb_no_trade() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "*", "mod*.json"))):
        doc = json.load(open(f))
        for nt in doc.get("no_trade_conditions") or []:
            out[nt["id"]] = " ".join(nt["statement"].split())
    return out


NT_TEXT = _kb_no_trade()


def _kb_rules() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "*", "mod*.json"))):
        doc = json.load(open(f))
        for r in doc.get("rules") or []:
            txt = r.get("statement") or r.get("rule") or ""
            out[r["id"]] = " ".join(str(txt).split())
    return out


RULE_TEXT = _kb_rules()


# ---------------------------------------------------------------------------
# source-element addressing
# ---------------------------------------------------------------------------
def src(sid: str, block: str, key) -> Dict[str, Any]:
    s = SPEC[sid]
    if block == "context":
        text = s["context"][key]
    elif block in ("prerequisites", "setup_sequence"):
        text = s[block][key]
    elif block == "entry.entry_zone":
        text = s["entry"]["entry_zone"]
    elif block == "entry.trigger_options":
        text = s["entry"]["trigger_options"][key]
    elif block == "stop_invalidation":
        text = s["stop_invalidation"][key]
    elif block == "target":
        text = s["target"][key]
    elif block == "session":
        text = s["session"]
    elif block == "direction":
        text = s["direction"]
    elif block == "parameters":
        p = s["parameters"][key]
        text = p["value"] if isinstance(p, dict) else str(p)
    elif block == "no_trade_conditions":
        text = NT_TEXT.get(key) or RULE_TEXT[key]
    else:
        raise KeyError(block)
    return {"block": block, "index": key, "text": text}


def elements(sid: str) -> List[Dict[str, Any]]:
    """Every specification element the coverage audit must account for."""
    s = SPEC[sid]
    out = [{"block": "context", "index": k} for k in s["context"]]
    out += [{"block": "prerequisites", "index": i} for i in range(len(s["prerequisites"]))]
    out += [{"block": "setup_sequence", "index": i} for i in range(len(s["setup_sequence"]))]
    out += [{"block": "entry.entry_zone", "index": "entry_zone"}]
    out += [{"block": "entry.trigger_options", "index": i}
            for i in range(len(s["entry"]["trigger_options"]))]
    out += [{"block": "stop_invalidation", "index": k} for k in s["stop_invalidation"]]
    out += [{"block": "target", "index": k} for k in s["target"]]
    out += [{"block": "session", "index": "session"}]
    return out


# ---------------------------------------------------------------------------
# node / parameter constructors
# ---------------------------------------------------------------------------
def node(nid, kind, source, kb_refs, primitives, expr, **kw) -> Dict[str, Any]:
    n = {"node_id": nid, "kind": kind, "source": source, "kb_refs": list(kb_refs),
         "primitives": list(primitives), "expr": expr}
    n.update({k: v for k, v in kw.items() if v is not None})
    return n


def unsupported(item_id, sid, source, element, reason, explanation, kb_refs,
                blocks_execution, resolution) -> Dict[str, Any]:
    return {"item_id": item_id, "strategy_id": sid, "source": source, "element": element,
            "reason_code": reason, "explanation": explanation, "kb_refs": list(kb_refs),
            "blocks_execution": bool(blocks_execution), "resolution": resolution}


def unconstrained(source, note) -> Dict[str, Any]:
    return {"source": source, "note": note}


PARAM_LIB: Dict[str, Dict[str, Any]] = {
    "governing_swing_tier": dict(
        binding="frozen_choice", choices=["short_term", "intermediate", "long_term"],
        kb_status="unspecified", kb_value="judgment informed by the ST/IT/LT hierarchy",
        source=["BEG-M03-C02", "INT-M01-R02"], register_id="governing_structural_point_tier"),
    "displacement_range_multiple": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="'unusually large relative to recent candles'",
        source=["BEG-M05-R01"], register_id="displacement_range_multiple"),
    "displacement_lookback": dict(
        binding="frozen_required", kb_status="unspecified", kb_value="-",
        source=["BEG-M05-R01"], register_id="displacement_lookback_candles"),
    "displacement_body_ratio_min": dict(
        binding="frozen_required", kb_status="heuristic_unfixed",
        kb_value="~60-70% cited by secondary tools; the book does not fix it",
        source=["BEG-M05-C01", "BEG-M05-C02", "BEG-M05-AMB01"],
        register_id="displacement_body_to_range_min"),
    "sweep_min_penetration": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="research parameter 'Y' in the knowledge base's own template",
        source=["ADV-M18-C03"], register_id="sweep_min_penetration"),
    "sweep_reclaim_bars": dict(
        binding="frozen_required", kb_status="alternatives_documented",
        kb_value="~2-3 lower-timeframe candles (Judas) / 'reasonable number' (PO3) / 'Z' bars",
        source=["BEG-M08-R06", "BEG-M09-R02", "ADV-M18-C03"], register_id="sweep_reclaim_window"),
    "equal_level_tolerance": dict(
        binding="frozen_required", kb_status="heuristic_unfixed",
        kb_value="~5-10 pips forex cited by secondary sources; 'obvious at a glance'",
        source=["BEG-M04-C05", "INT-M02-R01"], register_id="equal_highs_lows_tolerance"),
    "fib_anchor": dict(
        binding="frozen_choice", choices=["body", "wick"], kb_status="alternatives_documented",
        kb_value="body-to-body (BEG-M07-R01) vs liquidity-sweep wick origin (INT-M07-R01)",
        source=["BEG-M07-R01", "INT-M07-R01"], register_id="fib_anchor_price_type"),
    "ote_levels": dict(
        binding="frozen_choice", choices=[[0.62, 0.705, 0.79], [0.618, None, 0.786]],
        kb_status="alternatives_documented", kb_value="0.62/0.705/0.79 vs 0.618/0.786",
        source=["BEG-M07-R03", "INT-M07-R02"], register_id="ote_levels"),
    "entry_level": dict(
        binding="frozen_choice", choices=["fvg_ce", "ob_boundary"],
        kb_status="alternatives_documented",
        kb_value="consequent encroachment vs order-block boundary, both named in the same step",
        source=["BEG-M11-S01", "INT-M04-R02", "ADV-M16-R03"], register_id="target_policy"),
    "entry_trigger": dict(
        binding="frozen_choice", choices=["limit_at_zone", "ltf_confirmation"],
        kb_status="alternatives_documented",
        kb_value="resting limit at the zone (beginner) vs lower-timeframe confirmation required (advanced)",
        source=["BEG-M11-S01", "ADV-M16-R02", "ADV-M16-NT01"], register_id="stop_reference"),
    "ltf_confirmation_signal": dict(
        binding="frozen_choice", choices=["ltf_mss"], kb_status="specified_examples",
        kb_value="1-minute MSS or a rejection candle; only the MSS form is defined",
        source=["BEG-M11-S01"], register_id="ltf_confirmation_signal"),
    "stop_buffer_ticks": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="'just beyond' / 'small buffer' (examples ~12 pips EUR/USD, ~0.60 pts gold)",
        source=["BEG-M11-EX01", "BEG-M12-EX01"], register_id="stop_buffer"),
    "first_target_allocation": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="'e.g. 50% or a fixed fraction' — the fraction is never stated",
        source=["ADV-M16-R06"], register_id="partial_fraction"),
    "risk_fraction": dict(
        binding="frozen_required", kb_status="range_given",
        kb_value="~1% (max ~2%) beginner | 0.5-1% intermediate | 0.25-1% advanced",
        source=["BEG-M13-R01", "INT-M12-R01", "ADV-M17-R02"], register_id="risk_per_trade"),
    "asian_window_ET": dict(
        binding="frozen_choice", choices=[["20:00", "22:00"], ["20:00", "00:00"]],
        kb_status="alternatives_documented", kb_value="20:00-22:00 | 20:00-00:00",
        source=["BEG-M08-R01", "INT-M09-R01"], register_id="asian_window_ET"),
    "london_open_kz_ET": dict(
        binding="frozen_choice", choices=[["02:00", "05:00"], ["02:00", "04:00"]],
        kb_status="alternatives_documented", kb_value="02:00-05:00 | 02:00-04:00",
        source=["BEG-M08-R02", "INT-M09-R02", "ADV-M07-R01"], register_id="london_open_kz_ET"),
    "new_york_open_kz_ET": dict(
        binding="frozen_choice",
        choices=[["07:00", "10:00"], ["08:00", "11:00"], ["08:30", "11:00"], ["07:00", "09:00"]],
        kb_status="alternatives_documented", kb_value="four documented windows; unresolved",
        source=["BEG-M08-R04", "INT-M09-R03", "ADV-M07-R01", "BEG-M08-AMB01"],
        register_id="new_york_open_kz_ET"),
    "london_close_kz_ET": dict(
        binding="frozen_choice", choices=[["10:00", "12:00"], ["08:00", "09:00"]],
        kb_status="alternatives_documented", kb_value="non-overlapping alternatives; unresolved",
        source=["BEG-M08-R03", "BEG-M08-AMB02"], register_id="london_close_kz_ET"),
    "daily_open_definition": dict(
        binding="frozen_choice", choices=["new_york_midnight", "instrument_daily_open"],
        kb_status="alternatives_documented",
        kb_value="daily open (primary) vs New York midnight (thinner support)",
        source=["ADV-M07-C03", "ADV-M07-AMB01"], register_id="daily_open_definition"),
    "daily_bias_method": dict(
        binding="frozen_choice", choices=["three_factor", "single_mss"],
        kb_status="alternatives_documented",
        kb_value="three-factor (primary) vs the single-MSS 'daily bias trick'",
        source=["BEG-M10-C03", "BEG-M10-AMB01"], register_id="daily_bias_method"),
    "decisive_close_definition": dict(
        binding="frozen_choice",
        choices=["body_close_beyond", "body_close_beyond_by_ticks", "full_body_beyond"],
        kb_status="unspecified", kb_value="'decisive' close; the magnitude is never stated",
        source=["INT-M04-R03", "ADV-M06-R03", "INT-M11-R04"], register_id="fvg_failure_close"),
    "decisive_close_min_ticks": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="only needed when decisive_close_definition = body_close_beyond_by_ticks",
        source=["INT-M04-R03"], register_id="fvg_failure_close"),
    "breaker_test": dict(
        binding="frozen_choice", choices=["body_close", "sweep_plus_mss"],
        kb_status="alternatives_documented",
        kb_value="body close through the far boundary (INT-M05-R02) vs sweep + MSS (BEG-M06-R03)",
        source=["INT-M05-R02", "BEG-M06-R03"], register_id="breaker_test"),
    "reclaim_definition": dict(
        binding="frozen_choice",
        choices=["close_back_beyond_level", "wick_back_beyond_level",
                 "close_back_beyond_level_plus_buffer"],
        kb_status="unspecified",
        kb_value="no passage defines the price test that constitutes a reclaim (CF-14)",
        source=["BEG-M08-R06"], register_id="reclaim_definition"),
    "reclaim_buffer": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="only needed when reclaim_definition = close_back_beyond_level_plus_buffer",
        source=["BEG-M08-R06"], register_id="reclaim_definition"),
    "inversion_hold_definition": dict(
        binding="frozen_choice", choices=["retest_then_close_beyond_zone_without_decisive_break"],
        kb_status="unspecified",
        kb_value="'demonstrably holding' is never given a price test",
        source=["ADV-M06-R03"], register_id="ifvg_demonstration"),
    "smt_correlation_min": dict(
        binding="frozen_required", kb_status="unspecified",
        kb_value="'strong, stable correlation on the timeframe analysed'",
        source=["ADV-M13-R01"], register_id="smt_correlation_stability"),
    "smt_swing_comparison_window": dict(
        binding="frozen_required", kb_status="unspecified", kb_value="-",
        source=["ADV-M13-R02"], register_id="smt_correlation_stability"),
    "deep_zone_fraction": dict(
        binding="frozen_choice", choices=[0.20, 0.25], kb_status="range_given",
        kb_value="roughly the outer 20-25% of the range",
        source=["INT-M06-R02"], register_id="deep_premium_discount_zone"),
    "stop_reference_framework": dict(
        binding="frozen_choice", choices=["displacement_origin", "range_boundary"],
        kb_status="alternatives_documented",
        kb_value="displacement origin, or the dealing-range extreme if that was the structural reference",
        source=["INT-M06-S01", "INT-M12-R02", "ADV-M16-R04"], register_id="stop_reference"),
    "stop_reference_advanced": dict(
        binding="frozen_choice", choices=["displacement_origin", "array_far_side", "ltf_swing"],
        kb_status="alternatives_documented",
        kb_value="displacement origin | far side of the entry array | recent lower-timeframe swing",
        source=["ADV-M16-R04", "INT-M12-R02"], register_id="stop_reference"),
    "stop_scope": dict(
        binding="frozen_choice", choices=["ltf_tight", "htf_wide"],
        kb_status="alternatives_documented",
        kb_value="lower-timeframe array/displacement origin (tight) vs higher-timeframe array far side (wide)",
        source=["INT-M08-EX01", "ADV-M05-C10", "ADV-M16-R04"], register_id="stop_reference"),
    "rr_minimum": dict(
        binding="frozen_choice", choices=["none", 2.0, 3.0], kb_status="alternatives_documented",
        kb_value="1:2 / 1:3 as minimum thresholds (INT-M12-R03) vs no R:R filter at all (ADV-M17-R04)",
        source=["INT-M12-R03", "ADV-M17-R04"], register_id="rr_minimum_filter"),
    "stop_reference_po3": dict(
        binding="frozen_choice", choices=["manipulation_extreme", "displacement_origin"],
        kb_status="alternatives_documented",
        kb_value="below/above the manipulation extreme, or the displacement origin",
        source=["BEG-M09-S01", "P-STOP-01", "INT-M11-EX01"], register_id="stop_reference"),
    "extension_target": dict(
        binding="frozen_choice", choices=["ext_27", "ext_62"], kb_status="specified",
        kb_value="negative Fibonacci extensions -27% and -62%",
        source=["BEG-M07-R03", "INT-M07-R02"], register_id="fib_extension_targets"),
    "entry_level_ote": dict(
        binding="frozen_choice", choices=["ote_sweet", "array_overlap_boundary"],
        kb_status="alternatives_documented",
        kb_value="'often the 70.5% level or the boundary of the overlapping PD array'",
        source=["BEG-M07-S01", "INT-M07-C06"], register_id="target_policy"),
    "stop_reference_ote": dict(
        binding="frozen_choice", choices=["fib_origin", "conservative_ob_or_79"],
        kb_status="alternatives_documented",
        kb_value="just beyond the 100% level, or the more conservative of the order-block extreme and 79%",
        source=["BEG-M07-C06", "INT-M07-C06"], register_id="stop_reference"),
    "stop_reference_lokz": dict(
        binding="frozen_choice",
        choices=["swept_asian_extreme", "displacement_origin", "beyond_both"],
        kb_status="alternatives_documented",
        kb_value="beyond the swept Asian extreme | below the London displacement origin | beyond both",
        source=["BEG-M11-S01", "INT-M09-EX01", "INT-M12-EX01"], register_id="stop_reference"),
    "authorised_kill_zone_ET": dict(
        binding="frozen_choice",
        choices=[["02:00", "05:00"], ["02:00", "04:00"], ["07:00", "10:00"], ["08:00", "11:00"],
                 ["08:30", "11:00"], ["07:00", "09:00"]],
        kb_status="alternatives_documented",
        kb_value="the kill zone the daily narrative assigned to distribution/continuation "
                 "(typically London Open or New York Open); both have documented boundary variants",
        source=["ADV-M16-R07", "BEG-M08-R02", "BEG-M08-R04"], register_id="london_open_kz_ET"),
    "stop_reference_breaker": dict(
        binding="frozen_choice", choices=["breaker_extreme", "displacement_origin"],
        kb_status="alternatives_documented",
        kb_value="close back beyond the Breaker extreme, or beyond the origin of the displacement that created it",
        source=["ADV-M11-S02", "ADV-M12-S02"], register_id="stop_reference"),
    "max_daily_risk": dict(
        binding="frozen_required", kb_status="range_given", kb_value="e.g. 1-2% of equity",
        source=["ADV-M17-R03"], register_id="max_daily_risk"),
    "daily_loss_limit": dict(
        binding="frozen_required", kb_status="range_given", kb_value="e.g. 1-3% of equity",
        source=["ADV-M17-R03"], register_id="daily_loss_limit"),
    "accumulation_window_ET": dict(
        binding="frozen_choice", choices=[["20:00", "22:00"], ["20:00", "00:00"]],
        kb_status="alternatives_documented",
        kb_value="the accumulation range is the Asian session range; the window has two forms",
        source=["BEG-M09-C05", "INT-M10-R01", "BEG-M08-R01"], register_id="asian_window_ET"),
}


def params(*names) -> List[Dict[str, Any]]:
    out = []
    for n in names:
        if n not in PARAM_LIB:
            raise KeyError(f"parameter '{n}' is not in PARAM_LIB")
        out.append({"name": n, **PARAM_LIB[n]})
    return out


CORE = ("governing_swing_tier", "displacement_range_multiple", "displacement_lookback",
        "displacement_body_ratio_min", "sweep_min_penetration", "sweep_reclaim_bars",
        "equal_level_tolerance", "risk_fraction", "stop_buffer_ticks",
        "first_target_allocation")


# ---------------------------------------------------------------------------
# expression helpers
# ---------------------------------------------------------------------------
def C(v):
    return ["const", v]


def PARAM(n):
    return ["param", n]


def BIND(n, field=None):
    return ["binding", n] + ([field] if field else [])


def FEAT(name, **kw):
    return ["feature", name, kw]


def STATE(_state_id, **kw):
    return ["state", _state_id, kw]


def BAR(tf, component="close"):
    return FEAT("bar", tf=tf, component=component)


def STRUCT(tf):
    return STATE("structure", tf=tf, field="state")


def PDLOC(range_tf, price_tf):
    return FEAT("pd_location", tf=range_tf, price_tf=price_tf)


def POOLS(tf, side, kinds, select="nearest", field=None, session_window_param=None):
    kw = dict(tf=tf, side=side, kinds=list(kinds), select=select)
    if session_window_param:
        kw["session_window_param"] = session_window_param
    if field:
        kw["field"] = field
    return FEAT("liquidity_pools", **kw)


def DOL(direction, scope, tf, field=None):
    kw = dict(direction=direction, scope=scope, tf=tf)
    if field:
        kw["field"] = field
    return FEAT("dol", **kw)


def PO3(tf, period="daily"):
    return STATE("po3_state", tf=tf, accumulation_window_param="accumulation_window_ET",
                 period=period, field="phase")


OPP = {"bullish": "bearish", "bearish": "bullish"}
SIDE_OF = {"bullish": "sell", "bearish": "buy"}          # origin pool side
TARGET_SIDE = {"bullish": "buy", "bearish": "sell"}
POOL_SIDE_CODE = {"sell": "ssl", "buy": "bsl"}
HALF = {"bullish": "discount", "bearish": "premium"}
BEYOND = {"bullish": "below", "bearish": "above"}
LONG_SHORT = {"bullish": "long", "bearish": "short"}


# ---------------------------------------------------------------------------
# no-trade dispositions (shared across strategies)
# ---------------------------------------------------------------------------
DISPOSITIONS = {
    "ADV-M01-NT01": ("unsupported_subjective", "Retiring a model on delivery-leg failure requires a narrative rewrite judgment; the opposing-displacement-and-MSS half is mechanical but the 'target pool only partially probed' half is not."),
    "ADV-M02-NT01": ("compiled", "Lower-timeframe premium/discount conflicting with the controlling range."),
    "ADV-M03-NT01": ("unsupported_subjective", "Requires an explicit rewrite of the draw on liquidity; no mechanical test is given for when the rewrite is complete."),
    "ADV-M04-NT01": ("enforced_by_sequence", "Internal versus external MSS is separated by mss_scope; bias is read only on the higher timeframe; dealing-range location is a compiled gate."),
    "ADV-M05-NT01": ("enforced_by_sequence", "The setup sequence requires an array in the correct half aligned with the named draw; no array means no entry."),
    "ADV-M06-NT01": ("enforced_by_feature", "fvg_inverted requires a demonstrated hold after failure; the feature cannot label inversion at first trade-through."),
    "ADV-M06-NT02": ("compiled", "Entry array failed (traded through with opposing displacement)."),
    "ADV-M07-NT01": ("unsupported_subjective", "'Re-check the liquidity and structural narrative' is a review instruction, not a market condition."),
    "ADV-M08-NT01": ("compiled", "Power-of-3 phase gate: no directional entries during accumulation, and the manipulation move is not traded as the trend."),
    "ADV-M09-NT01": ("enforced_by_sequence", "The higher-timeframe bias gate is evaluated before any lower-timeframe setup can start."),
    "ADV-M10-NT01": ("compiled", "Bias unclear."),
    "ADV-M11-NT01": ("enforced_by_sequence", "Bias, discount location and the raid-then-displacement chain are all required steps."),
    "ADV-M12-NT01": ("enforced_by_sequence", "Mirror of ADV-M11-NT01."),
    "ADV-M13-NT01": ("enforced_by_feature", "smt_divergence requires a correlation test and is only ever a supporting layer; the primary entry model is unchanged."),
    "ADV-M14-NT01": ("compiled", "No aggressive directional entries during the Asian accumulation window."),
    "ADV-M15-NT01": ("compiled", "Distribution models forbidden during accumulation or early manipulation; the engine holds one position at a time, so a long and a short model cannot run together."),
    "ADV-M16-NT01": ("enforced_by_sequence", "Lower-timeframe confirmation is the entry trigger; the session window is a gate; the engine never widens a stop and never adds to a loser."),
    "ADV-M17-NT01": ("unsupported_process", "Overtrading is a behavioural failure, not a market condition."),
    "ADV-M17-NT02": ("compiled", "Higher-timeframe bias no longer supports the traded direction."),
    "ADV-M19-NT01": ("unsupported_process", "Final-stage process failures (writing the narrative stack, abandoning process)."),
    "BEG-M04-NT01": ("enforced_by_sequence", "A sweep alone never completes the sequence; displacement and MSS are separate required steps."),
    "BEG-M04-NT02": ("enforced_by_sequence", "The sweep step requires the raid classification, which is only assigned after the reversal prints."),
    "BEG-M05-NT01": ("enforced_by_feature", "The fair-value-gap registry only registers gaps whose middle candle qualifies as displacement."),
    "BEG-M07-NT01": ("enforced_by_sequence", "The retracement step must latch before the entry step is evaluated."),
    "BEG-M08-NT01": ("unsupported_process", "Disciplined inaction; no market condition to evaluate."),
    "BEG-M08-NT02": ("compiled", "No entries inside the Asian window."),
    "BEG-M09-NT01": ("compiled", "No entries while the Power-of-3 phase is accumulation."),
    "BEG-M09-NT02": ("enforced_by_sequence", "The lower-timeframe MSS is a required step before entry."),
    "BEG-M10-NT01": ("compiled", "Bias neutral or unclear."),
    "BEG-M11-NT01": ("enforced_by_sequence", "The bullish MSS step must latch before entry; without it the setup never completes."),
    "BEG-M11-NT02": ("enforced_by_sequence", "Every step of the chain is required, and the higher-timeframe context gate is re-checked at entry."),
    "BEG-M12-NT01": ("enforced_by_sequence", "Mirror of BEG-M11-NT01."),
    "BEG-M12-NT02": ("enforced_by_sequence", "Mirror of BEG-M11-NT02."),
    "BEG-M13-NT01": ("enforced_by_sequence", "A missing link means the setup machine never reaches the entry step."),
    "BEG-M13-NT02": ("unsupported_process", "'No trade' is the default outcome of the engine, and recording it as a process success is a journaling instruction."),
    "INT-M02-NT01": ("enforced_by_feature", "The sweep feature classifies raid versus continuation and only the raid classification advances the sequence."),
    "INT-M03-NT01": ("enforced_by_sequence", "Displacement and MSS are required steps."),
    "INT-M05-NT01": ("enforced_by_feature", "Array selection requires an unmitigated array; a fully mitigated order block is not offered."),
    "INT-M06-NT01": ("unsupported_subjective", "'Deep inside prolonged contraction' and 'chop' have no price test in the source."),
    "INT-M07-NT01": ("unsupported_subjective", "Clauses 1, 2 and 4 are enforced by the sequence (displacement required, bias gate, premium/discount filter); clauses 3 and 6 ('tight consolidation', 'low volatility with no kill-zone alignment') have no price test in the source."),
    "INT-M08-NT01": ("enforced_by_sequence", "The higher-timeframe bias gate cannot be overridden by a lower-timeframe signal."),
    "INT-M09-NT01": ("compiled", "No entries inside the Asian window or in the dead zones named by the specification."),
    "INT-M09-NT02": ("compiled", "No clear narrative: bias unclear."),
    "INT-M10-NT01": ("compiled", "Power-of-3 failure signature."),
    "INT-M11-NT01": ("compiled", "Bias unclear."),
    "INT-M11-NT02": ("enforced_by_sequence", "Only the daily/higher-timeframe bias authorises a direction."),
    "INT-M12-NT01": ("enforced_by_engine", "The engine sizes from the frozen risk fraction only, never widens a stop, never adds to a position, and rejects a stop that does not sit beyond the structural premise."),
}


def nt_expr(nt_id: str, info: Dict[str, Any]):
    """Expression that is TRUE when the no-trade condition applies."""
    htf, ltf, d = info["htf"], info["ltf"], info["direction"]
    if nt_id in ("BEG-M10-NT01",):
        return ["==", STATE("bias_state", tf=htf, method="daily", field="direction"), C("neutral")]
    if nt_id in ("INT-M11-NT01", "ADV-M10-NT01"):
        return ["or",
                ["==", STATE("bias_state", tf=htf, method="structural", field="direction"), C("unclear")],
                ["not", ["exists", DOL(d, "erl", htf)]],
                ["==", PDLOC(htf, ltf), C("equilibrium")]]
    if nt_id == "INT-M09-NT02":
        return ["==", STATE("bias_state", tf=htf, method="structural", field="direction"), C("unclear")]
    if nt_id in ("BEG-M08-NT02", "INT-M09-NT01", "ADV-M14-NT01"):
        return FEAT("in_session", window_param="asian_window_ET")
    if nt_id == "BEG-M09-NT01":
        return ["==", PO3(info["po3_tf"]), C("accumulation")]
    if nt_id in ("ADV-M08-NT01", "ADV-M15-NT01"):
        return ["in", PO3(info["po3_tf"]), C(["accumulation", "manipulation"])]
    if nt_id == "INT-M10-NT01":
        return ["==", PO3(info["po3_tf"]), C("failed")]
    if nt_id == "ADV-M02-NT01":
        return ["!=", PDLOC(htf, ltf), C(HALF[d])]
    if nt_id == "ADV-M06-NT02":
        return ["==", FEAT("fvg_state", tf=ltf, zone=BIND("array")), C("failed")]
    if nt_id == "ADV-M17-NT02":
        return ["!=", STATE("bias_state", tf=htf, method="structural", field="direction"), C(d)]
    raise KeyError(nt_id)


def nt_block(sid: str, info: Dict[str, Any], compile_ids: List[str]):
    """Compiled no-trade nodes plus the disposition record for every listed condition."""
    nodes, records, extra_unsupported = [], [], []
    short = sid.split("-")[0]
    for k, nt_id in enumerate(SPEC[sid]["no_trade_conditions"]):
        if nt_id not in NT_TEXT:
            records.append({"kb_ref": nt_id, "disposition": "not_a_no_trade_object",
                            "note": "listed by the specification but is a rule object, not a no-trade object"})
            continue
        disp, note = DISPOSITIONS[nt_id]
        if disp == "compiled" and nt_id in compile_ids:
            nid = f"{short}.nt.{nt_id}"
            nodes.append(node(nid, "predicate", src(sid, "no_trade_conditions", nt_id),
                              [nt_id], ["P-GATE-01"], nt_expr(nt_id, info)))
            records.append({"kb_ref": nt_id, "disposition": "compiled", "node_id": nid, "note": note})
        elif disp == "compiled":
            records.append({"kb_ref": nt_id, "disposition": "enforced_by_sequence",
                            "note": note + " (already implied by this strategy's own steps)"})
        elif disp.startswith("unsupported"):
            reason = ("UNSUPPORTED_PROCESS" if disp == "unsupported_process"
                      else "UNSUPPORTED_SUBJECTIVE")
            item = unsupported(
                f"U-{short}-NT-{nt_id}", sid, src(sid, "no_trade_conditions", nt_id),
                f"no-trade condition {nt_id}", reason, note, [nt_id], False,
                "Record it in the run report; it is not evaluated by the engine.")
            if reason == "UNSUPPORTED_SUBJECTIVE":
                item["effect_if_unenforced"] = (
                    "The run may include trades the specification would have stood aside from; "
                    "reported selectivity is therefore an upper bound.")
            extra_unsupported.append(item)
            records.append({"kb_ref": nt_id, "disposition": disp,
                            "unsupported_item_id": item["item_id"], "note": note})
        else:
            records.append({"kb_ref": nt_id, "disposition": disp, "note": note})
    return nodes, records, extra_unsupported


# ---------------------------------------------------------------------------
# document assembly
# ---------------------------------------------------------------------------
from strategy_compiler.engine.dsl import collect as _collect  # noqa: E402


def _direction(text: str) -> str:
    t = text.strip()
    if t.startswith("reversal_bidirectional"):
        return "reversal_bidirectional"
    if t.startswith("long or short") or t.startswith("long/short") or t.startswith("long and short"):
        return "either"
    if t.startswith("long"):
        return "long"
    if t.startswith("short"):
        return "short"
    return "either"


def assemble(sid, timeframes, data_req, parameters, blocks, unsupported_items,
             unconstrained_items, nt_records, primitives, extra=None):
    s = SPEC[sid]
    doc = {
        "dsl_version": "1.0.0",
        "strategy_id": sid,
        "name": s["name"],
        "kind": s["strategy_kind"],
        "parent_strategy_id": s.get("parent_strategy_id"),
        "direction": _direction(s["direction"]),
        "provenance": {
            "spec_file": "strategy_reearcher/catalog/strategies.json",
            "spec_strategy_id": sid,
            "kb_source_strategy_ids": s["kb_source_strategy_ids"],
            "primitives": sorted(set(primitives)),
            "specificity_status": s["specificity_status"],
            "spec_unspecified_elements": s.get("unspecified_elements", []),
            "spec_worked_example": s.get("worked_example"),
        },
        "timeframes": timeframes,
        "data_requirements": data_req,
        "parameters": parameters,
        "features": [],
        "market_state": [],
        "blocks": blocks,
        "no_trade_dispositions": nt_records,
        "unsupported": unsupported_items,
        "unconstrained": unconstrained_items,
        "executability": "executable",
        "blocking_items": [],
    }
    if extra:
        doc.update(extra)
    trig = [t["trigger_id"] for t in (blocks.get("entry") or {}).get("triggers") or []]
    if len(trig) > 1:
        for prm in doc["parameters"]:
            if prm["name"] == "entry_trigger":
                prm["choices"] = trig
                prm["kb_value"] = (
                    "the documented entry triggers for this specification: " + " | ".join(trig))
    used = _collect(doc)
    doc["features"] = sorted(used["features"])
    doc["market_state"] = sorted(used["states"])
    blocking = sorted(u["item_id"] for u in unsupported_items if u["blocks_execution"])
    doc["blocking_items"] = blocking
    doc["executability"] = "blocked" if blocking else "executable"
    return doc


def tfmap(**roles):
    return {k: v for k, v in roles.items()}


def tf(purpose, candidates, source, optional=False, min_history=200):
    d = {"purpose": purpose, "candidates": list(candidates), "source": list(source),
         "min_history": min_history}
    if optional:
        d["optional"] = True
    return d


def datareq(roles, period_opens, warmup=200, correlated=0, external=None, session_anchored=True):
    warmup = 200          # engine-side guard only; per-role history is in bars[].min_history
    return {
        "instrument": "primary",
        "correlated_instruments": correlated,
        "bars": {r: {"min_history": roles[r]["min_history"]} for r in roles},
        "timezone": "America/New_York",
        "session_anchored": session_anchored,
        "requires_period_opens": list(period_opens),
        "external_data": list(external or []),
        "warmup_bars": warmup,
    }


# ---------------------------------------------------------------------------
# family 1 — the eleven-step buy / sell models (S01, S02)
# ---------------------------------------------------------------------------
def build_eleven_step(sid):
    s = SPEC[sid]
    d = "bullish" if s["direction"] == "long" else "bearish"
    o, half, beyond = OPP[d], HALF[d], BEYOND[d]
    origin_side = SIDE_OF[d]                       # 'sell' for a long
    code = POOL_SIDE_CODE[origin_side]             # 'ssl'
    x = sid[:3]
    prim = ["P-STRUCT-01", "P-MSS-01", "P-LIQ-01", "P-LIQ-02", "P-DISP-01", "P-FVG-01",
            "P-OB-01", "P-FIB-01", "P-RANGE-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]

    roles = tfmap(
        htf=tf("higher-timeframe bias and structure (daily)", ["1d"], ["BEG-M11-S01"], min_history=90),
        htf_intermediate=tf("higher-timeframe bias and structure (4-hour)", ["4h"], ["BEG-M11-S01"], min_history=180),
        ltf_structure=tf("MSS, fair value gap and order block", ["15m", "5m"], ["BEG-M11-S01"], min_history=400),
        ltf_confirmation=tf("optional entry trigger", ["1m"], ["BEG-M11-S01"], optional=True, min_history=400),
    )

    pools = POOLS("ltf_structure", origin_side,
                  ["swing", "equal", "session_extreme", "prev_day"], "nearest",
                  session_window_param="asian_window_ET")
    bias_expr = ["or",
                 ["and", ["==", STRUCT("htf"), C(d)], ["==", STRUCT("htf_intermediate"), C(d)]],
                 FEAT("mss", tf="htf", direction=d)]

    ctx_loc_text = s["context"]["location"]
    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["BEG-M10-C02", "BEG-M03-C03", "BEG-M03-C04", "BEG-M03-C05"],
             ["P-STRUCT-01", "P-MSS-01"], bias_expr),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["BEG-M07-C02", "INT-M06-R02"], ["P-RANGE-01"],
             ["==", PDLOC("htf", "ltf_structure"), C(half)],
             gate=("stronger" not in ctx_loc_text.lower()),
             emits={"htf_pd_location": PDLOC("htf", "ltf_structure")}),
        node(f"{x}.ctx.pool", "predicate", src(sid, "context", "other"),
             ["BEG-M04-C03", "BEG-M04-C04"], ["P-LIQ-01"], ["exists", pools]),
    ]

    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["BEG-M11-S01", "BEG-M03-C03", "BEG-M03-C04"], ["P-STRUCT-01", "P-RANGE-01"],
             bias_expr, emits={"htf_pd_half": PDLOC("htf", "ltf_structure")}),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M04-C03", "BEG-M04-C04", "BEG-M04-C05", "BEG-M08-C03"], ["P-LIQ-01"],
             ["exists", pools],
             emits={"origin_pool": pools,
                    "origin_level": POOLS("ltf_structure", origin_side,
                                          ["swing", "equal", "session_extreme", "prev_day"],
                                          "nearest", field="price",
                                          session_window_param="asian_window_ET"),
                    "origin_from_index": POOLS("ltf_structure", origin_side,
                                               ["swing", "equal", "session_extreme", "prev_day"],
                                               "nearest", field="from_index",
                                               session_window_param="asian_window_ET")}),
    ]

    sweep = FEAT("sweep", tf="ltf_structure", level=BIND("origin_level"), side=code,
                 since_index=BIND("origin_from_index"))
    fvg = FEAT("fvg", tf="ltf_structure", direction=d, since_index=BIND("sweep_index"), select="latest")
    ob = FEAT("order_block", tf="ltf_structure", displacement_index=BIND("displacement_index"), direction=d)
    leg = lambda f: FEAT("displacement_leg", tf="ltf_structure",
                         at_index=BIND("displacement_index"), direction=d, field=f)
    fib = FEAT("fib_levels",
               origin=["if", ["==", PARAM("fib_anchor"), C("wick")], BIND("sweep", "extreme"), leg("origin")],
               termination=leg("termination"))

    setup = [
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 0),
             ["BEG-M04-C07", "BEG-M04-C08", "BEG-M11-S01"], ["P-LIQ-02"],
             ["==", FEAT("sweep", tf="ltf_structure", level=BIND("origin_level"), side=code,
                         since_index=BIND("origin_from_index"), field="classification"), C("raid")],
             emits={"sweep": sweep,
                    "sweep_extreme": FEAT("sweep", tf="ltf_structure", level=BIND("origin_level"),
                                          side=code, since_index=BIND("origin_from_index"), field="extreme"),
                    "sweep_index": FEAT("sweep", tf="ltf_structure", level=BIND("origin_level"),
                                        side=code, since_index=BIND("origin_from_index"), field="sweep_index")}),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 1),
             ["BEG-M05-C01", "BEG-M05-R01"], ["P-DISP-01"],
             ["and", FEAT("displacement", tf="ltf_structure", at_index=-1, direction=d),
              [">", FEAT("latest_index", tf="ltf_structure"), BIND("sweep_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="ltf_structure")}),
        node(f"{x}.setup.05", "event", src(sid, "setup_sequence", 2),
             ["BEG-M03-C05", "BEG-M03-R01", "BEG-M03-R02"], ["P-MSS-01"],
             FEAT("mss", tf="ltf_structure", at_index=-1, direction=d),
             emits={"mss_index": FEAT("latest_index", tf="ltf_structure")},
             also_covers=[{"block": "stop_invalidation", "index": "pre_entry_invalidation"}]),
        node(f"{x}.setup.06", "event", src(sid, "setup_sequence", 3),
             ["BEG-M05-C04", "BEG-M05-R02", "BEG-M06-C01"], ["P-FVG-01", "P-OB-01"],
             ["exists", fvg],
             emits={"array": fvg, "order_block": ob,
                    "array_ob_overlap": FEAT("zone_overlap", zone_a=fvg, zone_b=ob)}),
        node(f"{x}.setup.07", "event", src(sid, "setup_sequence", 4),
             ["BEG-M01-C08", "BEG-M07-C05"], ["P-FVG-01"],
             ["<=", BAR("ltf_structure", "low"), BIND("array", "high")] if d == "bullish"
             else [">=", BAR("ltf_structure", "high"), BIND("array", "low")]),
        node(f"{x}.setup.08", "event", src(sid, "setup_sequence", 5),
             ["BEG-M07-C03", "BEG-M07-C04", "BEG-M07-R01", "BEG-M07-R03"], ["P-FIB-01"],
             FEAT("in_ote", fib=fib, zone=BIND("array")),
             emits={"fib": fib}),
    ]

    entry_zone = node(
        f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
        ["BEG-M07-C06", "INT-M04-R02", "BEG-M06-C01"], ["P-FVG-01", "P-OB-01", "P-FIB-01"],
        ["if", ["==", PARAM("entry_level"), C("fvg_ce")], BIND("array", "ce"),
         BIND("order_block", "high" if d == "bullish" else "low")],
        emits={"entry_zone": C("$value")})

    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M11-S01", "INT-M04-R02"], ["P-FVG-01"],
             FEAT("in_ote", fib=BIND("fib"), price=BIND("entry_zone")),
             trigger_id="limit_at_zone",
             fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event", src(sid, "entry.trigger_options", 1),
             ["BEG-M11-S01", "BEG-M03-C05", "ADV-M16-R02"], ["P-MSS-01", "P-GATE-01"],
             ["and",
              FEAT("in_ote", fib=BIND("fib"), price=BIND("entry_zone")),
              ["<=", BAR("ltf_structure", "low"), BIND("entry_zone")] if d == "bullish"
              else [">=", BAR("ltf_structure", "high"), BIND("entry_zone")],
              ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf_confirmation", at_index=-1, direction=d)],
             trigger_id="ltf_confirmation",
             fill={"mode": "market_on_close"}),
    ]

    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M11-S01", "BEG-M12-S01"], ["P-STOP-01"],
                FEAT("offset", price=BIND("sweep", "extreme"),
                     ticks=PARAM("stop_buffer_ticks"), direction=beyond))

    tgt_side = TARGET_SIDE[d]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["BEG-M04-C03", "BEG-M04-C04", "BEG-M11-S01"], ["P-TARGET-01", "P-LIQ-01"],
             POOLS("ltf_structure", tgt_side, ["swing", "equal", "prev_day", "prev_week"],
                   "nearest", field="price"),
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["BEG-M04-C09", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             DOL(d, "erl", "htf", field="price"), allocation=0.0),
    ]

    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["BEG-M13-R01", "INT-M12-R01", "ADV-M17-R02"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]

    info = {"htf": "htf", "ltf": "ltf_structure", "direction": d, "po3_tf": "ltf_structure"}
    nt_nodes, nt_records, nt_unsupported = nt_block(sid, info, ["BEG-M10-NT01"])

    unsup = list(nt_unsupported)
    unsup.append(unsupported(
        f"U-{x}-01", sid, src(sid, "entry.trigger_options", 1),
        "'rejection candle' as an alternative lower-timeframe confirmation",
        "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
        "The step offers '1-minute bullish MSS or a rejection candle'. The MSS form is fully "
        "defined by BEG-M03-R01/R02 and is implemented; 'rejection candle' is never defined "
        "anywhere in the knowledge base, so it is not offered as a selectable value.",
        ["BEG-M11-S01"], False,
        "Select ltf_confirmation_signal = 'ltf_mss', or supply a definition and record it as a "
        "research operationalisation (ADV-M18-C03)."))

    uncon = [
        unconstrained(src(sid, "stop_invalidation", "narrative_level"),
                      "The specification states this element is unspecified in this module; there "
                      "is no rule to compile. Narrative-level invalidation is supplied by the "
                      "bias-conditioned variants (S19/S20) and the advanced models."),
        unconstrained(src(sid, "session", "session"),
                      "The generic statement imposes no session filter, so no session gate is "
                      "compiled. The worked example's session is recorded in provenance only."),
    ]

    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": [], "no_trade": nt_nodes, "risk": risk}

    pars = params(*CORE, "fib_anchor", "ote_levels", "entry_level", "entry_trigger",
                  "ltf_confirmation_signal", "asian_window_ET", "daily_bias_method",
                  "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=400),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# coverage audit (also used by tools/audit_translation.py)
# ---------------------------------------------------------------------------
from strategy_compiler.engine.dsl import iter_nodes as _iter_nodes  # noqa: E402


def coverage(doc) -> Dict[str, Any]:
    sid = doc["strategy_id"]
    covered: Dict[tuple, List[str]] = {}

    def mark(block, index, by):
        covered.setdefault((block, index), []).append(by)

    for _, n in _iter_nodes(doc):
        mark(n["source"]["block"], n["source"]["index"], n["node_id"])
        for a in n.get("also_covers", []):
            mark(a["block"], a["index"], n["node_id"])
    for u in doc["unsupported"]:
        mark(u["source"]["block"], u["source"]["index"], u["item_id"])
    for u in doc["unconstrained"]:
        mark(u["source"]["block"], u["source"]["index"], "unconstrained")

    missing, verbatim_errors = [], []
    for el in elements(sid):
        if (el["block"], el["index"]) not in covered:
            missing.append(el)
    for _, n in _iter_nodes(doc):
        s = n["source"]
        try:
            expected = src(sid, s["block"], s["index"])["text"]
        except Exception:
            continue
        if expected != s["text"]:
            verbatim_errors.append(n["node_id"])
    extra = [f"{b}:{i}" for (b, i) in covered
             if b not in ("parameters", "no_trade_conditions", "direction")
             and {"block": b, "index": i} not in elements(sid)]
    return {"strategy_id": sid, "missing_elements": missing,
            "verbatim_errors": verbatim_errors, "unmatched_nodes": extra,
            "elements_total": len(elements(sid)), "covered": len(covered)}


def _sweep_of(tf, side, kinds, field, session_window_param=None):
    code = POOL_SIDE_CODE[side]
    return FEAT("sweep", tf=tf,
                level=POOLS(tf, side, kinds, "nearest", field="price",
                            session_window_param=session_window_param),
                side=code,
                since_index=POOLS(tf, side, kinds, "nearest", field="from_index",
                                  session_window_param=session_window_param),
                field=field)


# ---------------------------------------------------------------------------
# family 2 — dealing-range frameworks (S03, S04)
# ---------------------------------------------------------------------------
def build_framework(sid):
    s = SPEC[sid]
    d = "bullish" if s["direction"] == "long" else "bearish"
    o, half, beyond = OPP[d], HALF[d], BEYOND[d]
    origin_side, tgt_side = SIDE_OF[d], TARGET_SIDE[d]
    x = sid[:3]
    prim = ["P-BIAS-02", "P-RANGE-01", "P-LIQ-01", "P-LIQ-02", "P-DISP-01", "P-MSS-01",
            "P-MSS-02", "P-FVG-01", "P-OB-01", "P-DOL-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("bias and the large dealing range", ["1d", "4h"], ["INT-M06-S01"], min_history=120),
        intermediate=tf("active dealing range and PD arrays", ["1h", "15m"], ["INT-M06-S01"], min_history=400),
        ltf=tf("entry timing", ["5m", "1m"], ["INT-M06-S01", "INT-M01-R05"], min_history=600),
    )
    rng = lambda f: FEAT("dealing_range", tf="intermediate", field=f)
    pools_kinds = ["swing", "equal", "prev_day"]
    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["INT-M11-R01", "ADV-M10-R01"], ["P-BIAS-02"],
             ["!=", STATE("bias_state", tf="htf", method="structural", field="direction"), C(o)]),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["INT-M06-C02", "INT-M06-R02", "INT-M02-R05"], ["P-RANGE-01", "P-LIQ-02"],
             ["or", ["==", PDLOC("intermediate", "ltf"), C(half)],
              ["==", _sweep_of("ltf", origin_side, pools_kinds, "classification"), C("raid")]]),
        node(f"{x}.ctx.range", "predicate", src(sid, "context", "other"),
             ["INT-M06-R01", "ADV-M02-R01"], ["P-RANGE-01"],
             ["exists", FEAT("dealing_range", tf="intermediate")],
             emits={"range_high": rng("high"), "range_low": rng("low"),
                    "range_equilibrium": rng("equilibrium")}),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["INT-M06-C01", "INT-M06-C02", "INT-M06-R02"], ["P-RANGE-01"],
             ["and", ["exists", FEAT("dealing_range", tf="intermediate")],
              ["==", PDLOC("intermediate", "ltf"), C(half)]]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["INT-M02-R05", "BEG-M04-C08"], ["P-LIQ-01", "P-LIQ-02"],
             ["==", _sweep_of("ltf", origin_side, pools_kinds, "classification"), C("raid")],
             emits={"raid": _sweep_of("ltf", origin_side, pools_kinds, "side"),
                    "raid_extreme": _sweep_of("ltf", origin_side, pools_kinds, "extreme"),
                    "raid_index": _sweep_of("ltf", origin_side, pools_kinds, "sweep_index")}),
        node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
             ["INT-M02-C05", "INT-M02-R02", "INT-M02-R04", "ADV-M03-R03"], ["P-DOL-01"],
             ["or", ["exists", DOL(d, "irl", "intermediate")], ["exists", DOL(d, "erl", "htf")]],
             emits={"dol_irl": DOL(d, "irl", "intermediate", field="price"),
                    "dol_erl": DOL(d, "erl", "htf", field="price")}),
    ]
    fvg = FEAT("fvg", tf="intermediate", direction=d, since_index=BIND("raid_index"), select="latest")
    ob = FEAT("order_block", tf="intermediate", displacement_index=BIND("displacement_index"), direction=d)
    leg = lambda f: FEAT("displacement_leg", tf="intermediate",
                         at_index=BIND("displacement_index"), direction=d, field=f)
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["INT-M03-R01", "INT-M03-R03", "INT-M03-R04", "BEG-M05-R01"],
             ["P-DISP-01", "P-MSS-01", "P-MSS-02"],
             ["and", FEAT("displacement", tf="intermediate", at_index=-1, direction=d),
              FEAT("mss", tf="intermediate", at_index=-1, direction=d),
              [">", FEAT("latest_index", tf="intermediate"), BIND("raid_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="intermediate"),
                    "mss_scope": FEAT("mss_scope", tf="intermediate", at_index=-1, range_tf="htf")}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["INT-M06-R03", "INT-M04-R04", "INT-M05-R01", "BEG-M05-C04"], ["P-FVG-01", "P-OB-01"],
             ["and", ["exists", fvg],
              ["==", FEAT("pd_location", tf="intermediate",
                          price=FEAT("midpoint", zone=fvg)), C(half)]],
             emits={"array": fvg, "order_block": ob}),
    ]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["INT-M06-R03", "INT-M04-R02"], ["P-FVG-01"],
                      BIND("array", "ce"), emits={"entry_zone": C("$value")})
    reach = (["<=", BAR("intermediate", "low"), BIND("array", "high")] if d == "bullish"
             else [">=", BAR("intermediate", "high"), BIND("array", "low")])
    triggers = [
        node(f"{x}.entry.trigger.ce", "event", src(sid, "entry.trigger_options", 0),
             ["INT-M04-R02", "ADV-M05-R01"], ["P-FVG-01"], reach,
             trigger_id="limit_at_zone", fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.ltf", "event", src(sid, "entry.trigger_options", 0),
             ["INT-M01-R05", "ADV-M16-R02"], ["P-MSS-01", "P-GATE-01"],
             ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf", at_index=-1, direction=d)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"},
             compilation_note="The specification names both refinements inside one trigger option "
                              "('refined by Consequent Encroachment or by LTF confirmation'); they "
                              "are compiled as two selectable arms of the same source element."),
    ]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["INT-M06-S01", "INT-M12-R02", "ADV-M16-R04"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_framework"), C("displacement_origin")],
                 FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                 FEAT("offset", price=rng("low" if d == "bullish" else "high"),
                      ticks=PARAM("stop_buffer_ticks"), direction=beyond)],
                execution_mode="close")
    invalidation = [
        node(f"{x}.inval.narrative", "predicate", src(sid, "stop_invalidation", "narrative_level"),
             ["INT-M11-R04", "INT-M06-R01"], ["P-RANGE-01", "P-BIAS-02"],
             ["<", BAR("intermediate", "close"), rng("low")] if d == "bullish"
             else [">", BAR("intermediate", "close"), rng("high")]),
    ]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["INT-M02-C07", "INT-M06-S01"], ["P-TARGET-01", "P-DOL-01"],
             DOL(d, "irl", "intermediate", field="price"),
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["INT-M02-C05", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             DOL(d, "erl", "htf", field="price"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["INT-M12-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": d, "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["INT-M11-NT01"])
    unsup = list(nt_unsup) + [unsupported(
        f"U-{x}-01", sid, src(sid, "context", "other"),
        "'prefer ranges whose both boundaries have been tested or had liquidity engineered'",
        "UNSUPPORTED_SUBJECTIVE",
        "The range-selection procedure states a preference, not a threshold: how much testing or "
        "engineering qualifies is never stated. The compiled node requires only that a dealing "
        "range exists on the intermediate timeframe.",
        ["INT-M06-R01", "ADV-M02-R01"], False,
        "Stratify results by whether both boundaries had been swept, rather than filtering on it.")]
    unsup[-1]["effect_if_unenforced"] = ("Ranges the specification would have rejected as "
                                         "un-engineered are included; selectivity is overstated.")
    uncon = [unconstrained(src(sid, "session", "session"),
                           "The specification states the session filter is unspecified. The "
                           "no-trade condition it cites (INT-M06-NT01) is registered separately as "
                           "an unsupported subjective condition.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "entry_trigger", "ltf_confirmation_signal",
                  "stop_reference_framework", "decisive_close_definition", "daily_bias_method",
                  "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=600),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 3 — Power of 3 daily template (S05)
# ---------------------------------------------------------------------------
def build_po3_daily(sid="S05-PO3-DAILY"):
    s = SPEC[sid]
    x = "S05"
    prim = ["P-PO3-01", "P-TIME-01", "P-TIME-02", "P-LIQ-02", "P-DISP-01", "P-MSS-01",
            "P-FVG-01", "P-OB-01", "P-RANGE-01", "P-DOL-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("daily bias, controlling range and draw on liquidity", ["1d"],
               ["INT-M10-R04", "ADV-M08-R04"], min_history=120),
        ltf=tf("accumulation range, manipulation sweep, MSS and entry array; the specification "
               "leaves this timeframe unspecified and cites 5-minute in its session examples",
               ["5m"], ["BEG-M09-S01", "INT-M10-R03"], min_history=800),
    )
    acc = lambda f: FEAT("session_range", tf="ltf", window_param="accumulation_window_ET", field=f)
    sw_lo = lambda f: FEAT("sweep", tf="ltf", level=acc("low"), side="ssl",
                           since_index=acc("end_index"), field=f)
    sw_hi = lambda f: FEAT("sweep", tf="ltf", level=acc("high"), side="bsl",
                           since_index=acc("end_index"), field=f)
    long_manip = ["==", sw_lo("classification"), C("raid")]
    short_manip = ["==", sw_hi("classification"), C("raid")]
    dirw = BIND("dir_word")

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["INT-M10-R04", "ADV-M08-R04", "BEG-M09-S01"], ["P-BIAS-02", "P-PO3-01"],
             ["!=", STATE("bias_state", tf="htf", method="structural", field="direction"), C("unclear")],
             gate=False,
             emits={"htf_bias": STATE("bias_state", tf="htf", method="structural", field="direction")},
             compilation_note="BEG-M09-S01 states no bias precondition; INT-M10-R04/ADV-M08-R04 "
                              "call alignment a quality grading ('highest quality when ...'), so "
                              "this node grades and does not veto."),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["INT-M10-R04", "ADV-M08-R04"], ["P-RANGE-01"],
             ["exists", FEAT("dealing_range", tf="htf")], gate=False,
             emits={"controlling_half": PDLOC("htf", "ltf")}),
        node(f"{x}.ctx.open_and_range", "predicate", src(sid, "context", "other"),
             ["ADV-M07-C03", "BEG-M08-C03"], ["P-TIME-02"],
             ["and", ["exists", FEAT("period_open", period="daily", tf="ltf")],
              ["exists", FEAT("session_range", tf="ltf", window_param="accumulation_window_ET")]],
             emits={"daily_open": FEAT("period_open", period="daily", tf="ltf")}),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["ADV-M07-C03", "ADV-M07-AMB01"], ["P-PO3-01"],
             ["exists", FEAT("period_open", period="daily", tf="ltf")]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M09-C01", "BEG-M08-C03", "BEG-M09-NT01"], ["P-PO3-01", "P-TIME-02"],
             ["and", ["exists", FEAT("session_range", tf="ltf", window_param="accumulation_window_ET")],
              ["not", FEAT("in_session", window_param="accumulation_window_ET")]],
             emits={"acc_high": acc("high"), "acc_low": acc("low"), "acc_end": acc("end_index")}),
    ]
    fvg = FEAT("fvg", tf="ltf", direction=dirw, since_index=BIND("manip_index"), select="latest")
    ob = FEAT("order_block", tf="ltf", displacement_index=BIND("displacement_index"), direction=dirw)
    leg = lambda f: FEAT("displacement_leg", tf="ltf", at_index=BIND("displacement_index"),
                         direction=dirw, field=f)
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M09-C02", "BEG-M09-R02", "INT-M10-C05", "ADV-M08-R03"], ["P-PO3-01", "P-LIQ-02"],
             ["or", long_manip, short_manip],
             emits={"trade_direction": ["if", long_manip, C("long"), C("short")],
                    "dir_word": ["if", long_manip, C("bullish"), C("bearish")],
                    "manip_extreme": ["if", long_manip, sw_lo("extreme"), sw_hi("extreme")],
                    "manip_index": ["if", long_manip, sw_lo("sweep_index"), sw_hi("sweep_index")]}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M09-C03", "BEG-M03-C05", "BEG-M05-C01"], ["P-DISP-01", "P-MSS-01"],
             ["and", FEAT("displacement", tf="ltf", at_index=-1, direction=dirw),
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw),
              [">", FEAT("latest_index", tf="ltf"), BIND("manip_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="ltf")}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["INT-M10-R03", "ADV-M08-R03", "BEG-M05-C04", "BEG-M06-C01"], ["P-FVG-01", "P-OB-01"],
             ["exists", fvg], emits={"array": fvg, "order_block": ob}),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR("ltf", "low"), BIND("array", "high")],
             [">=", BAR("ltf", "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["INT-M10-R03", "INT-M04-R02"], ["P-FVG-01"], BIND("array", "ce"),
                      emits={"entry_zone": C("$value")})
    triggers = [node(f"{x}.entry.trigger", "event", src(sid, "entry.trigger_options", 0),
                     ["BEG-M09-S01", "BEG-M09-NT02"], ["P-MSS-01"], reach,
                     trigger_id="after_ltf_mss",
                     fill={"mode": "limit", "price": BIND("entry_zone")},
                     compilation_note="The MSS requirement is the preceding setup step, so this "
                                      "trigger can only fire after it has latched; entering during "
                                      "the manipulation move is structurally impossible.")]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M09-S01", "INT-M11-EX01", "BEG-M11-S01"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_po3"), C("manipulation_extreme")],
                 FEAT("offset", price=BIND("manip_extreme"), ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]),
                 FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")])])
    invalidation = [node(f"{x}.inval.pattern", "predicate",
                         src(sid, "stop_invalidation", "pattern_invalidation"),
                         ["BEG-M09-R02", "INT-M10-R05", "ADV-M08-R05"], ["P-PO3-01"],
                         ["==", PO3("ltf"), C("failed")])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["BEG-M09-C03", "INT-M10-R01"], ["P-PO3-01", "P-TARGET-01"],
             ["if", ["==", dirw, C("bullish")], BIND("acc_high"), BIND("acc_low")],
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["INT-M10-R01", "ADV-M03-R03"], ["P-DOL-01", "P-TARGET-01"],
             FEAT("dol", direction=dirw, scope="erl", tf="htf", field="price"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["BEG-M13-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(
        sid, info, ["BEG-M09-NT01", "INT-M10-NT01", "ADV-M08-NT01", "BEG-M08-NT02", "INT-M09-NT01"])
    unsup = list(nt_unsup) + [unsupported(
        "U-S05-01", sid, src(sid, "prerequisites", 1),
        "'relatively tight, roughly horizontal' accumulation range", "UNSUPPORTED_SUBJECTIVE",
        "The specification requires the accumulation range to be tight and roughly horizontal but "
        "gives no measure of tightness. The compiled node uses the session range as marked, "
        "without a shape test.",
        ["BEG-M09-C01"], False,
        "Stratify by realised range width rather than filtering on it.")]
    unsup[-1]["effect_if_unenforced"] = (
        "Days whose Asian session was not a tight range are still labelled as accumulation; the "
        "population is broader than the specification intends.")
    uncon = [unconstrained(src(sid, "session", "session"),
                           "The specification calls the Asia/London/New York phase mapping a "
                           "tendency, not a law, and says the phases may shift around major news. "
                           "No session gate is compiled; the accumulation window parameter is what "
                           "anchors the phases.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "accumulation_window_ET", "asian_window_ET",
                  "stop_reference_po3", "daily_open_definition", "daily_bias_method")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=800),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 4 — Judas Swing, London Open (S06)
# ---------------------------------------------------------------------------
def build_judas(sid="S06-JUDAS-LONDON"):
    s = SPEC[sid]
    x = "S06"
    prim = ["P-TIME-01", "P-TIME-02", "P-LIQ-02", "P-DISP-01", "P-MSS-01", "P-FVG-01",
            "P-FIB-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("bias stratification only (not a filter at this level)", ["1d"],
               ["BEG-M08-S01", "INT-M11-C03"], min_history=120),
        ltf=tf("Asian range, sweep, displacement, MSS, reclaim count and entry array",
               ["5m"], ["BEG-M08-S01", "BEG-M08-R06"], min_history=800),
    )
    ar = lambda f: FEAT("session_range", tf="ltf", window_param="asian_window_ET", field=f)
    sw_lo = lambda f: FEAT("sweep", tf="ltf", level=ar("low"), side="ssl",
                           since_index=ar("end_index"), field=f)
    sw_hi = lambda f: FEAT("sweep", tf="ltf", level=ar("high"), side="bsl",
                           since_index=ar("end_index"), field=f)
    long_manip = ["==", sw_lo("classification"), C("raid")]
    dirw = BIND("dir_word")

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["BEG-M08-S01", "INT-M11-C03", "ADV-M10-R03"], ["P-BIAS-02"],
             ["!=", STATE("bias_state", tf="htf", method="structural", field="direction"), C("unclear")],
             gate=False,
             emits={"htf_bias": STATE("bias_state", tf="htf", method="structural", field="direction")},
             compilation_note="The specification states there is no higher-timeframe precondition "
                              "in this base form and directs that bias alignment be a "
                              "stratification variable, so this node records and does not veto. "
                              "The bias-conditioned form is S19/S20."),
        node(f"{x}.ctx.range", "predicate", src(sid, "context", "other"),
             ["BEG-M08-C03", "BEG-M08-C04"], ["P-TIME-02"],
             ["exists", FEAT("session_range", tf="ltf", window_param="asian_window_ET")]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["BEG-M08-R02", "BEG-M08-R05", "INT-M09-R02"], ["P-TIME-01"],
             FEAT("in_session", window_param="london_open_kz_ET"),
             also_covers=[{"block": "session", "index": "session"}]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M08-C03", "INT-M09-C01"], ["P-TIME-02"],
             ["exists", FEAT("session_range", tf="ltf", window_param="asian_window_ET")],
             emits={"asian_high": ar("high"), "asian_low": ar("low")}),
    ]
    fvg = FEAT("fvg", tf="ltf", direction=dirw, since_index=BIND("manip_index"), select="latest")
    leg = lambda f: FEAT("displacement_leg", tf="ltf", at_index=BIND("displacement_index"),
                         direction=dirw, field=f)
    fib = FEAT("fib_levels", origin=BIND("manip_extreme"), termination=leg("termination"))
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M04-C08", "BEG-M08-C06"], ["P-LIQ-02"],
             ["or", long_manip, ["==", sw_hi("classification"), C("raid")]],
             emits={"trade_direction": ["if", long_manip, C("long"), C("short")],
                    "dir_word": ["if", long_manip, C("bullish"), C("bearish")],
                    "manip_extreme": ["if", long_manip, sw_lo("extreme"), sw_hi("extreme")],
                    "manip_index": ["if", long_manip, sw_lo("sweep_index"), sw_hi("sweep_index")],
                    "manip_level": ["if", long_manip, ar("low"), ar("high")],
                    "manip_side": ["if", long_manip, C("ssl"), C("bsl")]}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M05-C01", "BEG-M05-R01"], ["P-DISP-01"],
             ["and", FEAT("displacement", tf="ltf", at_index=-1, direction=dirw),
              [">", FEAT("latest_index", tf="ltf"), BIND("manip_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="ltf")}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["BEG-M03-C05", "BEG-M03-R01"], ["P-MSS-01"],
             FEAT("mss", tf="ltf", at_index=-1, direction=dirw)),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
             ["BEG-M08-R06"], ["P-LIQ-02"],
             ["not", FEAT("level_reclaimed", tf="ltf", level=BIND("manip_level"),
                          side=BIND("manip_side"), from_index=BIND("manip_index"),
                          within_bars=PARAM("sweep_reclaim_bars"))],
             also_covers=[{"block": "stop_invalidation", "index": "pattern_invalidation"}]),
        node(f"{x}.setup.05", "event", src(sid, "setup_sequence", 4),
             ["BEG-M05-C04", "BEG-M07-C06"], ["P-FVG-01"],
             ["exists", fvg], emits={"array": fvg, "fib": fib}),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR("ltf", "low"), BIND("array", "high")],
             [">=", BAR("ltf", "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["BEG-M07-C06", "INT-M04-R02"], ["P-FVG-01", "P-FIB-01"],
                      BIND("array", "ce"), emits={"entry_zone": C("$value")})
    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M07-S01", "BEG-M11-S01"], ["P-FVG-01"], reach,
             trigger_id="limit_at_zone", fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M07-S01", "ADV-M16-R02"], ["P-MSS-01"],
             ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"},
             compilation_note="The single trigger option defers to BEG-M07-S01, which documents "
                              "both a resting limit and a confirmation entry; both arms are "
                              "compiled from that one source element."),
    ]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M07-C06", "BEG-M11-S01"], ["P-STOP-01"],
                FEAT("offset", price=BIND("manip_extreme"), ticks=PARAM("stop_buffer_ticks"),
                     direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]))
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["BEG-M08-C06", "BEG-M04-C03", "BEG-M04-C04"], ["P-TARGET-01", "P-TIME-02"],
             ["if", ["==", dirw, C("bullish")], BIND("asian_high"), BIND("asian_low")],
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["BEG-M07-R03", "INT-M07-R02"], ["P-FIB-01", "P-TARGET-01"],
             ["if", ["==", PARAM("extension_target"), C("ext_27")],
              ["field", BIND("fib"), "ext_27"], ["field", BIND("fib"), "ext_62"]],
             allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["BEG-M13-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["BEG-M08-NT02", "INT-M09-NT01", "INT-M09-NT02"])
    unsup = list(nt_unsup) + [
        unsupported("U-RECLAIM", sid, src(sid, "setup_sequence", 3),
                    "operational definition of 'reclaim'",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification counts the reclaim window in candles (~2-3) but no passage "
                    "in the knowledge base defines the price test that constitutes a reclaim "
                    "(CF-14). Three candidate tests are offered as a frozen choice; the engine "
                    "will not pick one.",
                    ["BEG-M08-R06"], True,
                    "Record an operationalisation for U-RECLAIM and set reclaim_definition (and "
                    "reclaim_buffer if the buffered form is chosen)."),
    ]
    uncon = [unconstrained(src(sid, "context", "location"),
                           "The specification states this element is unspecified in this module.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": [], "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "ote_levels", "extension_target", "asian_window_ET",
                  "london_open_kz_ET", "entry_trigger", "ltf_confirmation_signal",
                  "reclaim_definition", "daily_bias_method", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily"], warmup=800),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 5 — New York Open kill-zone sweep sequence (S07)
# ---------------------------------------------------------------------------
def build_nykz(sid="S07-NYKZ-SWEEP-SEQUENCE"):
    s = SPEC[sid]
    x = "S07"
    prim = ["P-TIME-01", "P-TIME-02", "P-LIQ-01", "P-LIQ-02", "P-DISP-01", "P-MSS-01",
            "P-FVG-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("session-to-session context (what Asia built and London did)", ["1d"],
               ["BEG-M08-C11"], min_history=120),
        ltf=tf("sweep, displacement, MSS and entry array; the specification leaves the timeframe "
               "unspecified and reads 5-minute by analogy with the London sequence",
               ["5m"], ["BEG-M08-S02"], min_history=800),
    )
    kinds = ["swing", "equal", "prev_day", "session_extreme"]
    sell_lvl = POOLS("ltf", "sell", kinds, "nearest", field="price",
                     session_window_param="london_open_kz_ET")
    buy_lvl = POOLS("ltf", "buy", kinds, "nearest", field="price",
                    session_window_param="london_open_kz_ET")
    sw_lo = lambda f: _sweep_of("ltf", "sell", kinds, f, "london_open_kz_ET")
    sw_hi = lambda f: _sweep_of("ltf", "buy", kinds, f, "london_open_kz_ET")
    long_manip = ["==", sw_lo("classification"), C("raid")]
    dirw = BIND("dir_word")

    context = [
        node(f"{x}.ctx.sessions", "predicate", src(sid, "context", "htf_bias_required"),
             ["BEG-M08-C11", "INT-M09-R05"], ["P-TIME-02"],
             ["exists", FEAT("session_range", tf="ltf", window_param="asian_window_ET")],
             gate=False,
             emits={"asian_range": FEAT("session_range", tf="ltf", window_param="asian_window_ET"),
                    "london_range": FEAT("session_range", tf="ltf", window_param="london_open_kz_ET")},
             compilation_note="The specification states no bias requirement here and asks only "
                              "that the session be read in relation to Asia and London, so this "
                              "node records those ranges and does not veto."),
        node(f"{x}.ctx.levels", "predicate", src(sid, "context", "other"),
             ["INT-M09-C05", "BEG-M04-C06"], ["P-LIQ-01"],
             ["and", ["exists", sell_lvl], ["exists", buy_lvl]]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["BEG-M08-R04", "INT-M09-R03", "ADV-M07-R01"], ["P-TIME-01"],
             FEAT("in_session", window_param="new_york_open_kz_ET"),
             also_covers=[{"block": "session", "index": "session"}]),
        node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
             ["INT-M09-C05", "BEG-M04-C06", "BEG-M08-C03"], ["P-LIQ-01", "P-TIME-02"],
             ["and", ["exists", sell_lvl], ["exists", buy_lvl]]),
    ]
    fvg = FEAT("fvg", tf="ltf", direction=dirw, since_index=BIND("sweep_index"), select="latest")
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M04-C08", "BEG-M08-C09"], ["P-LIQ-02"],
             ["or", long_manip, ["==", sw_hi("classification"), C("raid")]],
             emits={"trade_direction": ["if", long_manip, C("long"), C("short")],
                    "dir_word": ["if", long_manip, C("bullish"), C("bearish")],
                    "sweep_extreme": ["if", long_manip, sw_lo("extreme"), sw_hi("extreme")],
                    "sweep_index": ["if", long_manip, sw_lo("sweep_index"), sw_hi("sweep_index")]}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M05-C01", "BEG-M05-R01"], ["P-DISP-01"],
             ["and", FEAT("displacement", tf="ltf", at_index=-1, direction=dirw),
              [">", FEAT("latest_index", tf="ltf"), BIND("sweep_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="ltf")}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["BEG-M03-C05", "BEG-M08-S02"], ["P-MSS-01"],
             FEAT("mss", tf="ltf", at_index=-1, direction=dirw)),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR("ltf", "low"), BIND("array", "high")],
             [">=", BAR("ltf", "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["BEG-M08-S02", "BEG-M05-C04", "INT-M04-R02"], ["P-FVG-01"],
                      FEAT("midpoint", zone=fvg), emits={"entry_zone": C("$value"), "array": fvg},
                      compilation_note="'by analogy to S06' — the London sequence's displacement "
                                       "fair value gap and its consequent encroachment.")
    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M08-S02", "BEG-M07-S01"], ["P-FVG-01"], reach,
             trigger_id="limit_at_zone", fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M08-S02", "ADV-M16-R02"], ["P-MSS-01"],
             ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"}),
    ]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M08-S02", "BEG-M11-S01"], ["P-STOP-01"],
                FEAT("offset", price=BIND("sweep_extreme"), ticks=PARAM("stop_buffer_ticks"),
                     direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]))
    targets = [node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
                    ["INT-M09-R05", "BEG-M04-C03", "BEG-M04-C04"], ["P-TARGET-01", "P-LIQ-01"],
                    ["if", ["==", dirw, C("bullish")],
                     POOLS("ltf", "buy", kinds, "nearest", field="price",
                           session_window_param="london_open_kz_ET"),
                     POOLS("ltf", "sell", kinds, "nearest", field="price",
                           session_window_param="london_open_kz_ET")],
                    allocation=1.0)]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["INT-M12-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["INT-M09-NT02"])
    unsup = list(nt_unsup) + [
        unsupported("U-S07-01", sid, src(sid, "prerequisites", 1),
                    "scheduled US data release as a context input",
                    "UNSUPPORTED_EXTERNAL_DATA",
                    "The step asks the trader to note whether a scheduled release is imminent or "
                    "has just occurred. That requires an economic calendar, which is not price "
                    "data and which the specification does not define or bound.",
                    ["BEG-M08-S02", "INT-M12-R05"], False,
                    "Supply a calendar as a separate feed and stratify results by proximity to "
                    "releases; the step is a note, not a filter, so it is not compiled as a gate."),
        unsupported("U-S07-02", sid, src(sid, "stop_invalidation", "pattern_invalidation"),
                    "reclaim-based pre-entry invalidation",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification records this element as not restated in the source module "
                    "('by analogy'). Compiling the London reclaim test here would import a rule "
                    "the source did not state for this session, so it is left out.",
                    ["BEG-M08-S02", "BEG-M08-R06"], False,
                    "If the analogy is adopted, run S06's reclaim step explicitly and record it as "
                    "a research operationalisation."),
    ]
    unsup[-1]["effect_if_unenforced"] = (
        "Setups that London's rules would have discarded as genuine breakouts remain eligible "
        "here; the required MSS step is the only protection.")
    uncon = [unconstrained(src(sid, "context", "location"),
                           "The specification states this element is unspecified.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": [], "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "asian_window_ET", "london_open_kz_ET",
                  "new_york_open_kz_ET", "entry_trigger", "ltf_confirmation_signal",
                  "daily_bias_method", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=800),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 6 — London Close raid and retracement (S08) — blocked
# ---------------------------------------------------------------------------
def build_london_close(sid="S08-LONDON-CLOSE-RETRACE"):
    s = SPEC[sid]
    x = "S08"
    prim = ["P-TIME-01", "P-LIQ-02", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        ltf=tf("raid of the day's extreme and the retracement; the specification leaves the "
               "timeframe unspecified", ["5m"], ["BEG-M08-S03"], min_history=800),
    )
    day_hi = FEAT("session_range", tf="ltf", window_param="london_open_kz_ET", field="high")
    kinds = ["swing", "prev_day"]
    sw_hi = lambda f: _sweep_of("ltf", "buy", kinds, f)
    sw_lo = lambda f: _sweep_of("ltf", "sell", kinds, f)
    short_raid = ["==", sw_hi("classification"), C("raid")]
    dirw = BIND("dir_word")

    context = []
    prereq = [node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
                   ["BEG-M08-R03", "BEG-M08-AMB02", "INT-M09-R04"], ["P-TIME-01"],
                   FEAT("in_session", window_param="london_close_kz_ET"),
                   also_covers=[{"block": "session", "index": "session"}])]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M08-C07", "BEG-M04-C08"], ["P-LIQ-02"],
             ["or", short_raid, ["==", sw_lo("classification"), C("raid")]],
             emits={"trade_direction": ["if", short_raid, C("short"), C("long")],
                    "dir_word": ["if", short_raid, C("bearish"), C("bullish")],
                    "raid_extreme": ["if", short_raid, sw_hi("extreme"), sw_lo("extreme")],
                    "raid_index": ["if", short_raid, sw_hi("sweep_index"), sw_lo("sweep_index")]}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M08-C07", "ADV-M07-C03"], ["P-TIME-01"],
             ["if", ["==", dirw, C("bearish")],
              ["<", BAR("ltf", "close"), BIND("raid_extreme")],
              [">", BAR("ltf", "close"), BIND("raid_extreme")]],
             emits={"daily_open": FEAT("period_open", period="daily", tf="ltf")}),
    ]
    targets = [node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
                    ["BEG-M08-S03", "ADV-M07-C03"], ["P-TARGET-01"],
                    FEAT("period_open", period="daily", tf="ltf"), allocation=1.0)]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", "position_size"),
                 ["BEG-M08-R03", "INT-M12-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "ltf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["INT-M09-NT02"])
    unsup = list(nt_unsup) + [
        unsupported("U-S08-01", sid, src(sid, "context", "other"),
                    "'has already extended meaningfully in one direction'",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The precondition is a magnitude with no measure anywhere in the source; the "
                    "specification itself records extension_magnitude as unspecified.",
                    ["BEG-M08-S03"], True,
                    "Record an operationalisation for U-S08-01 (for example a minimum range in "
                    "ticks or in multiples of the Asian range) as a research parameter."),
        unsupported("U-S08-02", sid, src(sid, "prerequisites", 1),
                    "assessment that the day has already extended meaningfully",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "Same missing measure as U-S08-01, stated here as a prerequisite step.",
                    ["BEG-M08-S03"], True, "Resolved by the same operationalisation as U-S08-01."),
        unsupported("U-S08-03", sid, src(sid, "entry.entry_zone", "entry_zone"),
                    "entry zone", "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification says the entry zone is unspecified beyond 'liquidity raid "
                    "then retracement toward the day's open'. There is no level to compile.",
                    ["BEG-M08-S03"], True,
                    "Freeze an entry zone built only from documented components and report it as a "
                    "research operationalisation (ADV-M18-R01)."),
        unsupported("U-S08-04", sid, src(sid, "entry.trigger_options", 0),
                    "entry trigger", "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification explicitly hands the trigger to the researcher.",
                    ["BEG-M08-S03"], True,
                    "Freeze a trigger from documented components (for example displacement plus a "
                    "lower-timeframe MSS after the raid) and report it as an operationalisation."),
        unsupported("U-S08-05", sid, src(sid, "stop_invalidation", "trade_level"),
                    "trade-level invalidation", "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "Unspecified in this module; no stop reference is named.",
                    ["BEG-M08-S03"], True,
                    "Freeze one of the P-STOP-01 options and report it."),
        unsupported("U-S08-06", sid, src(sid, "parameters", "position_size"),
                    "'reduced' position size", "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification requires reduced size relative to primary setups but gives "
                    "no reduction factor.",
                    ["BEG-M08-R03"], False,
                    "Freeze a reduction factor and report it; the engine sizes from risk_fraction, "
                    "so set a smaller risk_fraction for this strategy."),
    ]
    uncon = [
        unconstrained(src(sid, "context", "htf_bias_required"), "Stated as unspecified."),
        unconstrained(src(sid, "context", "location"), "Stated as unspecified."),
        unconstrained(src(sid, "stop_invalidation", "narrative_level"), "Stated as unspecified."),
        unconstrained(src(sid, "target", "secondary"), "Stated as unspecified."),
    ]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": None, "triggers": []}, "stop": None,
              "targets": targets, "invalidation": [], "no_trade": nt_nodes, "risk": risk}
    pars = params("governing_swing_tier", "sweep_min_penetration", "sweep_reclaim_bars",
                  "equal_level_tolerance", "risk_fraction", "london_close_kz_ET",
                  "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily"], warmup=800),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 7 — OTE entry-zone component (S09)
# ---------------------------------------------------------------------------
def build_ote_component(sid="S09-OTE-ENTRY-COMPONENT"):
    s = SPEC[sid]
    x = "S09"
    prim = ["P-BIAS-01", "P-BIAS-02", "P-RANGE-01", "P-DISP-01", "P-MSS-01", "P-FIB-01",
            "P-FVG-01", "P-OB-01", "P-OB-02", "P-LIQ-02", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("bias and the dealing range the OTE band must sit in", ["1d", "4h"],
               ["BEG-M07-S01", "INT-M07-R03"], min_history=120),
        ltf=tf("the measured displacement leg, the OTE band and the confirmation signal; OTE is "
               "fractal so the specification fixes no timeframe", ["15m", "5m"],
               ["BEG-M07-C04"], min_history=800),
    )
    dirw = BIND("dir_word")
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    kinds = ["swing", "equal", "prev_day"]
    leg = lambda f: FEAT("displacement_leg", tf="ltf", at_index=BIND("displacement_index"),
                         direction=dirw, field=f)
    fib = FEAT("fib_levels", origin=leg("origin"), termination=leg("termination"))
    fvg = FEAT("fvg", tf="ltf", direction=dirw, since_index=BIND("displacement_index"), select="latest")
    ob = FEAT("order_block", tf="ltf", displacement_index=BIND("displacement_index"), direction=dirw)

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["BEG-M10-R01", "INT-M11-R01"], ["P-BIAS-01", "P-BIAS-02"],
             ["in", bias, C(["bullish", "bearish"])],
             emits={"dir_word": bias,
                    "trade_direction": ["if", ["==", bias, C("bullish")], C("long"), C("short")]}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["INT-M07-R03", "INT-M07-C03"], ["P-RANGE-01", "P-FIB-01"],
             ["==", PDLOC("htf", "ltf"),
              ["if", ["==", dirw, C("bullish")], C("discount"), C("premium")]],
             gate=False,
             compilation_note="INT-M07-R03 grades an OTE on the wrong side of equilibrium as lower "
                              "quality requiring extra confluence; it does not forbid it, so this "
                              "node records and does not veto."),
        node(f"{x}.ctx.leg", "predicate", src(sid, "context", "other"),
             ["BEG-M05-C01", "BEG-M03-C05", "BEG-M07-S01"], ["P-DISP-01", "P-MSS-01"],
             ["and", FEAT("displacement", tf="ltf", at_index=-1, direction=dirw),
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw)],
             emits={"displacement_index": FEAT("latest_index", tf="ltf")}),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["BEG-M07-S01", "BEG-M03-R02"], ["P-DISP-01", "P-MSS-01", "P-BIAS-02"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              FEAT("mss", tf="ltf", at_index=BIND("displacement_index"), direction=dirw)]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["INT-M07-C04", "BEG-M04-C08"], ["P-LIQ-02"],
             ["==", ["if", ["==", dirw, C("bullish")],
                     _sweep_of("ltf", "sell", kinds, "classification"),
                     _sweep_of("ltf", "buy", kinds, "classification")], C("raid")],
             gate=False,
             compilation_note="The specification says a preceding raid is 'preferable' and that "
                              "without it the retracement is lower probability; it is recorded, "
                              "not enforced."),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M07-R01", "INT-M07-R01", "INT-M07-C01"], ["P-FIB-01"],
             ["exists", fib], emits={"fib": fib}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M07-R03", "BEG-M07-C03"], ["P-FIB-01"],
             ["exists", ["field", BIND("fib"), "ote_start"]]),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["BEG-M07-C05", "BEG-M07-NT01"], ["P-FIB-01"],
             FEAT("in_ote", fib=BIND("fib"), price=BAR("ltf", "close"))),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
             ["INT-M07-C05", "INT-M07-C06", "BEG-M06-C01", "BEG-M05-C04"],
             ["P-FVG-01", "P-OB-01", "P-OB-02"],
             C(True),
             emits={"array": fvg, "order_block": ob,
                    "ote_array_overlap": FEAT("zone_overlap", zone_a=fvg, zone_b=ob)},
             compilation_note="The step is a confluence CHECK, not a filter: Module 7 trades the "
                              "OTE with or without an overlapping array and only grades the "
                              "confluence higher. Compiling it as a gate would add an entry "
                              "condition the source does not impose, so the node always latches "
                              "and records what it found."),
        node(f"{x}.setup.05", "event", src(sid, "setup_sequence", 4),
             ["BEG-M07-S01", "BEG-M11-S01", "BEG-M12-S01"], ["P-MSS-01"],
             ["and", ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw)]),
    ]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["BEG-M07-C06", "INT-M07-C06"], ["P-FIB-01", "P-OB-01"],
                      ["if", ["==", PARAM("entry_level_ote"), C("ote_sweet")],
                       ["field", BIND("fib"), "ote_sweet"],
                       FEAT("midpoint", zone=BIND("ote_array_overlap"))],
                      emits={"entry_zone": C("$value")})
    triggers = [node(f"{x}.entry.trigger", "event", src(sid, "entry.trigger_options", 0),
                     ["BEG-M07-S01"], ["P-MSS-01"],
                     FEAT("in_ote", fib=BIND("fib"), price=BIND("entry_zone")),
                     trigger_id="ltf_confirmation", fill={"mode": "market_on_close"})]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M07-C06", "INT-M07-C06"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_ote"), C("fib_origin")],
                 FEAT("offset", price=["field", BIND("fib"), "origin"],
                      ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]),
                 FEAT("offset",
                      price=FEAT("pick",
                                 values=[["field", BIND("order_block"), "low"],
                                         ["field", BIND("fib"), "ote_end"]],
                                 mode=["if", ["==", dirw, C("bullish")], C("min"), C("max")]),
                      ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")])])
    invalidation = [node(f"{x}.inval.ote", "predicate",
                         src(sid, "stop_invalidation", "pattern_invalidation"),
                         ["INT-M07-R04"], ["P-FIB-01"],
                         ["if", ["==", dirw, C("bullish")],
                          ["<", BAR("ltf", "close"), ["field", BIND("fib"), "origin"]],
                          [">", BAR("ltf", "close"), ["field", BIND("fib"), "origin"]]])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["BEG-M07-C06", "BEG-M04-C03", "BEG-M04-C04"], ["P-TARGET-01", "P-LIQ-01"],
             ["if", ["==", dirw, C("bullish")],
              POOLS("ltf", "buy", kinds, "nearest", field="price"),
              POOLS("ltf", "sell", kinds, "nearest", field="price")],
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["BEG-M07-R03", "INT-M07-R02"], ["P-FIB-01", "P-TARGET-01"],
             ["if", ["==", PARAM("extension_target"), C("ext_27")],
              ["field", BIND("fib"), "ext_27"], ["field", BIND("fib"), "ext_62"]],
             allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[-1]),
                 ["INT-M12-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, [])
    unsup = list(nt_unsup) + [unsupported(
        "U-S09-01", sid, src(sid, "setup_sequence", 4),
        "the lower-timeframe confirmation signal",
        "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
        "Module 7 does not define the confirmation signal and the specification defers it to "
        "Modules 11-12, where it is a lower-timeframe MSS. That defined form is compiled; the "
        "undefined 'rejection candle' form is not offered.",
        ["BEG-M07-S01", "BEG-M11-S01"], False,
        "Select ltf_confirmation_signal = 'ltf_mss', or define the alternative and record it.")]
    uncon = [unconstrained(src(sid, "session", "session"),
                           "Stated as unspecified in Module 7. The cited no-trade condition "
                           "INT-M07-NT01 is registered separately as unsupported subjective.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "ote_levels", "entry_level_ote", "stop_reference_ote",
                  "extension_target", "ltf_confirmation_signal")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=800),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 8 — daily scalping (S10) — blocked
# ---------------------------------------------------------------------------
def build_daily_scalp(sid="S10-DAILY-SCALP"):
    s = SPEC[sid]
    x = "S10"
    prim = ["P-BIAS-03", "P-LIQ-01", "P-LIQ-02", "P-DISP-01", "P-MSS-01", "P-FVG-01",
            "P-OB-01", "P-TIME-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("daily bias and the pools to be swept and targeted", ["1d", "4h"],
               ["BEG-M13-C01", "BEG-M13-C02"], min_history=120),
        ltf=tf("execution", ["5m", "3m", "1m"], ["BEG-M13-C05"], min_history=1000),
    )
    bias = STATE("bias_state", tf="htf", method="daily", field="direction")
    dirw = BIND("dir_word")
    kinds = ["swing", "equal", "prev_day"]
    fvg = FEAT("fvg", tf="ltf", direction=dirw, since_index=BIND("sweep_index"), select="latest")

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["BEG-M13-C02", "BEG-M10-R02", "BEG-M10-R03"], ["P-BIAS-03"],
             ["in", bias, C(["bullish", "bearish"])],
             emits={"dir_word": bias,
                    "trade_direction": ["if", ["==", bias, C("bullish")], C("long"), C("short")]}),
        node(f"{x}.ctx.draw", "predicate", src(sid, "context", "other"),
             ["BEG-M13-C03", "BEG-M13-C06"], ["P-LIQ-01", "P-DOL-01"],
             ["exists", FEAT("dol", direction=dirw, scope="any", tf="htf")]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["BEG-M13-C01", "BEG-M13-C02", "BEG-M13-C03"], ["P-BIAS-03", "P-LIQ-01"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              ["exists", ["if", ["==", dirw, C("bullish")],
                          POOLS("ltf", "sell", kinds, "nearest"),
                          POOLS("ltf", "buy", kinds, "nearest")]]],
             emits={"origin_level": ["if", ["==", dirw, C("bullish")],
                                     POOLS("ltf", "sell", kinds, "nearest", field="price"),
                                     POOLS("ltf", "buy", kinds, "nearest", field="price")],
                    "origin_from": ["if", ["==", dirw, C("bullish")],
                                    POOLS("ltf", "sell", kinds, "nearest", field="from_index"),
                                    POOLS("ltf", "buy", kinds, "nearest", field="from_index")]}),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M13-C04", "BEG-M08-R02", "BEG-M08-R04"], ["P-TIME-01"],
             FEAT("in_session", window_param="authorised_kill_zone_ET"),
             also_covers=[{"block": "session", "index": "session"}]),
    ]
    sw = lambda f: FEAT("sweep", tf="ltf", level=BIND("origin_level"),
                        side=["if", ["==", dirw, C("bullish")], C("ssl"), C("bsl")],
                        since_index=BIND("origin_from"), field=f)
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M13-C05", "BEG-M11-S01", "BEG-M12-S01"],
             ["P-LIQ-02", "P-DISP-01", "P-MSS-01", "P-FVG-01"],
             ["and", ["==", sw("classification"), C("raid")], ["exists", fvg]],
             emits={"sweep_index": sw("sweep_index"), "sweep_extreme": sw("extreme")}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M13-R02", "BEG-M13-C05"], ["P-MSS-01", "P-FVG-01", "P-STOP-01"],
             ["and", ["exists", fvg],
              FEAT("mss", tf="ltf", at_index=["field", fvg, "displacement_index"], direction=dirw),
              ["if", ["==", dirw, C("bullish")],
               ["<=", BAR("ltf", "low"), ["field", fvg, "high"]],
               [">=", BAR("ltf", "high"), ["field", fvg, "low"]]]],
             emits={"array": fvg},
             compilation_note="Items 1, 2 and 4 of the four-item checklist are compiled here "
                              "(clear liquidity draw, complete sweep-displace-MSS-retrace "
                              "sequence, defined invalidation). Item 3, the single-impulse "
                              "objective, has no measure in the source and is registered as "
                              "blocking unsupported item U-S10-01."),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR("ltf", "low"), BIND("array", "high")],
             [">=", BAR("ltf", "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["BEG-M13-C07", "BEG-M11-S01"], ["P-FVG-01"], BIND("array", "ce"),
                      emits={"entry_zone": C("$value")})
    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M13-C07"], ["P-FVG-01"], reach, trigger_id="limit_at_zone",
             fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M13-C07", "ADV-M16-R02"], ["P-MSS-01"],
             ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf", at_index=-1, direction=dirw)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"}),
    ]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M13-R02", "BEG-M11-S01"], ["P-STOP-01"],
                FEAT("offset", price=BIND("sweep_extreme"), ticks=PARAM("stop_buffer_ticks"),
                     direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]))
    invalidation = [node(f"{x}.inval.bias", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["BEG-M10-R04", "BEG-M13-C02"], ["P-BIAS-03"],
                         ["!=", bias, dirw])]
    targets = [node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
                    ["BEG-M13-S01", "BEG-M13-C03"], ["P-TARGET-01", "P-LIQ-01"],
                    ["if", ["==", dirw, C("bullish")],
                     POOLS("ltf", "buy", kinds, "nearest", field="price"),
                     POOLS("ltf", "sell", kinds, "nearest", field="price")], allocation=1.0)]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", "risk_per_trade"),
                 ["BEG-M13-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf", "direction": "bullish", "po3_tf": "ltf"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["BEG-M10-NT01"])
    unsup = list(nt_unsup) + [
        unsupported("U-S10-01", sid, src(sid, "setup_sequence", 1),
                    "checklist item 3: 'single-impulse objective'",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The checklist makes all four items mandatory, but neither 'nearby pool' nor "
                    "'single impulse' is given any measure; the specification itself records both "
                    "as unspecified. Deciding whether the nearest pool is reachable in one impulse "
                    "cannot be computed from the source.",
                    ["BEG-M13-R02", "BEG-M13-S01"], True,
                    "Record an operationalisation for U-S10-01 (for example a maximum distance to "
                    "the target pool in multiples of the stop distance) as a research parameter."),
        unsupported("U-S10-02", sid, src(sid, "parameters", "fragility_note"),
                    "transaction-cost sensitivity", "UNSUPPORTED_PROCESS",
                    "The specification requires transaction-cost modelling for this model. Spread "
                    "and slippage are instrument-configuration inputs to the engine, not strategy "
                    "logic, so this is a run-configuration obligation rather than a compiled rule.",
                    ["BEG-M13-R02"], False,
                    "Set non-zero spread and slippage in the instrument configuration and report "
                    "them alongside results."),
    ]
    uncon = [unconstrained(src(sid, "context", "location"),
                           "Stated as unspecified beyond the parent model."),
             unconstrained(src(sid, "target", "secondary"),
                           "The specification states there is no secondary target by definition.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "entry_trigger", "ltf_confirmation_signal",
                  "authorised_kill_zone_ET", "daily_bias_method", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=1000),
                    pars, blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# families 9-12 — advanced Buy/Sell model variations A-D (S11..S18)
# ---------------------------------------------------------------------------
def build_adv(sid, variation):
    s = SPEC[sid]
    d = "bullish" if s["direction"] == "long" else "bearish"
    o, half, beyond = OPP[d], HALF[d], BEYOND[d]
    origin_side, tgt_side = SIDE_OF[d], TARGET_SIDE[d]
    x = sid[:3]
    nested = variation == "D"
    ex = "ltf" if nested else "execution"
    prim = ["P-BIAS-02", "P-DOL-01", "P-RANGE-01", "P-LIQ-01", "P-LIQ-02", "P-DISP-01",
            "P-MSS-01", "P-FVG-01", "P-OB-01", "P-TIME-01", "P-GATE-01", "P-STOP-01",
            "P-TARGET-01", "P-RISK-01"]
    if variation == "B":
        prim.append("P-OB-02")
    if variation == "C":
        prim.append("P-FVG-02")

    if nested:
        roles = tfmap(
            htf=tf("weekly/daily array and draw on liquidity", ["1w", "1d"],
                   ["ADV-M11-S04", "INT-M08-R02"], min_history=120),
            intermediate=tf("nested range and arrays", ["4h", "1h"], ["INT-M08-R02"], min_history=400),
            ltf=tf("sweep, displacement, MSS and the nested entry array", ["15m", "5m"],
                   ["ADV-M11-S04"], min_history=1000),
        )
    else:
        roles = tfmap(
            htf=tf("monthly/weekly/daily narrative and the controlling range", ["1d", "1w"],
                   ["ADV-M10-R01", "ADV-M02-R01"], min_history=120),
            execution=tf("conditioning and entry", ["15m", "5m", "1m"],
                         ["ADV-M16-R02"], min_history=1000),
        )
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    kinds = ["swing", "equal", "prev_day", "prev_week"]
    dolx = DOL(d, "erl", "htf")
    raid = _sweep_of(ex, origin_side, kinds, "classification")

    permission = ["and", ["==", bias, C(d)], ["exists", dolx]]
    location = ["or", ["==", PDLOC("htf", ex), C(half)], ["==", raid, C("raid")]]
    in_kz = FEAT("in_session", window_param="authorised_kill_zone_ET")

    # --- variation-specific arrays -------------------------------------
    fvg_d = FEAT("fvg", tf=ex, direction=d, since_index=BIND("raid_index"), select="latest")
    ob_d = FEAT("order_block", tf=ex, displacement_index=BIND("displacement_index"), direction=d)
    leg = lambda f: FEAT("displacement_leg", tf=ex, at_index=BIND("displacement_index"),
                         direction=d, field=f)
    opp_fvg = FEAT("fvg", tf=ex, direction=o, select="latest")
    opp_ob = FEAT("order_block", tf=ex, displacement_index=["field", opp_fvg, "displacement_index"],
                  direction=o)
    htf_fvg = FEAT("fvg", tf="htf", direction=d, select="latest")
    ltf_fvg = FEAT("fvg", tf=ex, direction=d, since_index=BIND("raid_index"), select="latest")

    # --- context --------------------------------------------------------
    ctx_other = {
        "A": (["ADV-M08-R03", "ADV-M16-R07"], ["P-TIME-01", "P-PO3-01"], in_kz),
        "B": (["INT-M05-R03", "BEG-M06-R03"], ["P-OB-01", "P-OB-02"],
              ["==", FEAT("breaker_state", tf=ex, ob=opp_ob), C("breaker")]),
        "C": (["ADV-M06-R03", "INT-M04-R03"], ["P-FVG-02"],
              ["==", FEAT("fvg_state", tf=ex, zone=opp_fvg), C("failed")]),
        "D": (["INT-M08-R04"], ["P-FVG-01", "P-DOL-01"], ["exists", htf_fvg]),
    }[variation]
    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["ADV-M10-R01", "ADV-M10-R02", "ADV-M12-R01" if d == "bearish" else "ADV-M11-R01"],
             ["P-BIAS-02", "P-DOL-01"], permission,
             emits={"dol_erl": DOL(d, "erl", "htf", field="price"),
                    "dol_irl": DOL(d, "irl", "htf", field="price")}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["ADV-M02-R01", "ADV-M02-C06", "INT-M06-R02"], ["P-RANGE-01", "P-LIQ-02"], location),
        node(f"{x}.ctx.other", "predicate", src(sid, "context", "other"),
             ctx_other[0], ctx_other[1], ctx_other[2],
             gate=(variation != "D"),
             compilation_note=None if variation != "D" else
             "The clause states a division of labour (higher timeframe supplies the zone, lower "
             "timeframe only times the entry) rather than a condition; the node records that an "
             "unmitigated higher-timeframe array exists and does not veto."),
    ]

    # --- prerequisites ---------------------------------------------------
    npre = len(s["prerequisites"])
    prereq, pre_unsup = [], []
    checklist = ["and", permission, location, in_kz]
    if variation == "A":
        if npre == 3:
            pre_unsup.append(unsupported(
                f"U-{x}-NARRATIVE", sid, src(sid, "prerequisites", 0),
                "narrative stack written pre-session", "UNSUPPORTED_PROCESS",
                "Writing the monthly-weekly-daily narrative before the session is a process "
                "discipline, not a market condition. Its computable content (bias direction, "
                "range location, named draw on liquidity) is compiled in the context block.",
                ["ADV-M09-R03", "ADV-M10-R01"], False,
                "Record that the narrative stack was written; the engine evaluates its computable "
                "content only."))
            prereq += [
                node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
                     ["ADV-M10-R07", "ADV-M11-R02", "ADV-M16-R03"], ["P-BIAS-02", "P-FVG-01"],
                     ["and", ["==", bias, C(d)], ["==", PDLOC("htf", ex), C(half)]]),
                node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
                     ["ADV-M11-R01", "ADV-M16-R08"], ["P-GATE-01"], checklist),
            ]
        else:
            prereq += [
                node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
                     ["ADV-M10-R07", "ADV-M09-R03"], ["P-BIAS-02"], ["==", bias, C(d)]),
                node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
                     ["ADV-M12-R01", "ADV-M16-R08"], ["P-GATE-01"], checklist),
            ]
            pre_unsup.append(unsupported(
                f"U-{x}-NARRATIVE", sid, src(sid, "prerequisites", 0),
                "'narrative stack written' clause", "UNSUPPORTED_PROCESS",
                "The model-permission half of this step is compiled; writing the narrative stack "
                "is a process discipline with no market test.",
                ["ADV-M09-R03", "ADV-M10-R07"], False, "Record it in the run report."))
    elif variation in ("B", "C"):
        auth = (["==", FEAT("breaker_state", tf=ex, ob=opp_ob), C("breaker")] if variation == "B"
                else FEAT("fvg_inverted", tf=ex, zone=opp_fvg))
        prereq += [
            node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
                 ["ADV-M11-R01" if d == "bullish" else "ADV-M12-R01", "ADV-M16-R08"],
                 ["P-GATE-01"], checklist),
            node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
                 ["ADV-M11-R02", "ADV-M15-C04"],
                 ["P-OB-02"] if variation == "B" else ["P-FVG-02"], auth),
        ]
    else:                                                     # D
        htf_map = ["and", ["exists", FEAT("dealing_range", tf="htf")], ["exists", dolx]]
        int_map = ["exists", FEAT("dealing_range", tf="intermediate")]
        if npre == 3:
            prereq += [
                node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
                     ["INT-M08-R02", "ADV-M10-R01"], ["P-RANGE-01", "P-DOL-01"], htf_map),
                node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
                     ["INT-M08-R02"], ["P-RANGE-01"], int_map),
                node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
                     ["ADV-M11-R01", "ADV-M11-R02", "ADV-M15-C04"], ["P-GATE-01"], checklist),
            ]
        else:
            prereq += [
                node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
                     ["INT-M08-R02"], ["P-RANGE-01", "P-DOL-01"], ["and", htf_map, int_map]),
                node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
                     ["ADV-M12-R01", "ADV-M11-R02"], ["P-GATE-01"], checklist),
            ]
    prereq.append(node(f"{x}.pre.session", "predicate", src(sid, "session", "session"),
                       ["ADV-M16-R07"], ["P-TIME-01"], in_kz))

    # --- setup ------------------------------------------------------------
    nset = len(s["setup_sequence"])
    if variation == "A":
        setup = [
            node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
                 ["ADV-M03-R01", "BEG-M04-C08"], ["P-LIQ-02"], ["==", raid, C("raid")],
                 emits={"raid_index": _sweep_of(ex, origin_side, kinds, "sweep_index"),
                        "raid_extreme": _sweep_of(ex, origin_side, kinds, "extreme")}),
            node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
                 ["ADV-M04-R03", "BEG-M05-R01", "BEG-M03-R02"], ["P-DISP-01", "P-MSS-01", "P-MSS-02"],
                 ["and", FEAT("displacement", tf=ex, at_index=-1, direction=d),
                  FEAT("mss", tf=ex, at_index=-1, direction=d),
                  [">", FEAT("latest_index", tf=ex), BIND("raid_index")]],
                 emits={"displacement_index": FEAT("latest_index", tf=ex),
                        "mss_scope": FEAT("mss_scope", tf=ex, at_index=-1, range_tf="htf")}),
            node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
                 ["ADV-M05-R01", "INT-M06-R03", "BEG-M06-C01"], ["P-FVG-01", "P-OB-01", "P-FVG-02"],
                 ["and", ["exists", fvg_d],
                  ["==", FEAT("pd_location", tf="htf", price=FEAT("midpoint", zone=fvg_d)), C(half)],
                  ["!=", FEAT("fvg_state", tf=ex, zone=fvg_d), C("failed")]],
                 emits={"array": fvg_d, "order_block": ob_d}),
            node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
                 ["ADV-M06-R02"], ["P-FVG-01"],
                 ["<=", BAR(ex, "low"), BIND("array", "high")] if d == "bullish"
                 else [">=", BAR(ex, "high"), BIND("array", "low")]),
        ]
        zone_expr = BIND("array", "ce")
        stop_expr = ["if", ["==", PARAM("stop_reference_advanced"), C("displacement_origin")],
                     FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                     FEAT("offset", price=BIND("array", "low" if d == "bullish" else "high"),
                          ticks=PARAM("stop_buffer_ticks"), direction=beyond)]
    elif variation == "B":
        brk = ["==", FEAT("breaker_state", tf=ex, ob=opp_ob), C("breaker")]
        base = [
            node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
                 ["ADV-M03-R01", "BEG-M04-C08"], ["P-LIQ-02"], ["==", raid, C("raid")],
                 emits={"raid_index": _sweep_of(ex, origin_side, kinds, "sweep_index"),
                        "raid_extreme": _sweep_of(ex, origin_side, kinds, "extreme")}),
            node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
                 ["INT-M05-R02", "BEG-M06-R03", "ADV-M11-S02"], ["P-OB-02", "P-DISP-01", "P-MSS-01"],
                 ["and", brk, FEAT("mss", tf=ex, at_index=-1, direction=d)],
                 emits={"breaker": opp_ob,
                        "displacement_index": FEAT("latest_index", tf=ex)}),
        ]
        if nset == 4:
            base.append(node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
                             ["ADV-M15-C04", "INT-M05-C05", "ADV-M05-R05"], ["P-OB-02"],
                             brk, emits={"array": BIND("breaker")}))
            last_i = 3
        else:
            base[-1]["emits"]["array"] = opp_ob
            last_i = 2
        base.append(node(f"{x}.setup.{last_i + 1:02d}", "event", src(sid, "setup_sequence", last_i),
                         ["ADV-M11-S02", "ADV-M02-C06"], ["P-OB-02", "P-RANGE-01"],
                         ["and", ["==", PDLOC("htf", ex), C(half)],
                          ["<=", BAR(ex, "low"), BIND("array", "high")] if d == "bullish"
                          else [">=", BAR(ex, "high"), BIND("array", "low")]]))
        setup = base
        zone_expr = FEAT("midpoint", zone=BIND("array"))
        stop_expr = ["if", ["==", PARAM("stop_reference_breaker"), C("breaker_extreme")],
                     FEAT("offset", price=BIND("array", "low" if d == "bullish" else "high"),
                          ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                     FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"),
                          direction=beyond)]
    elif variation == "C":
        setup = [
            node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
                 ["BEG-M04-C08", "ADV-M03-R01"], ["P-LIQ-02"], ["==", raid, C("raid")],
                 emits={"raid_index": _sweep_of(ex, origin_side, kinds, "sweep_index"),
                        "raid_extreme": _sweep_of(ex, origin_side, kinds, "extreme")}),
            node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
                 ["INT-M04-R03", "ADV-M06-R03"], ["P-FVG-02"],
                 ["==", FEAT("fvg_state", tf=ex, zone=opp_fvg), C("failed")],
                 emits={"failed_gap": opp_fvg}),
            node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
                 ["ADV-M06-R03", "ADV-M06-C07"], ["P-FVG-02"],
                 FEAT("fvg_inverted", tf=ex, zone=BIND("failed_gap")),
                 emits={"array": BIND("failed_gap")}),
            node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
                 ["ADV-M11-S03", "ADV-M06-R02"], ["P-DISP-01"],
                 FEAT("displacement", tf=ex, at_index=-1, direction=d),
                 emits={"displacement_index": FEAT("latest_index", tf=ex)}),
        ]
        zone_expr = FEAT("midpoint", zone=BIND("array"))
        stop_expr = ["if", ["==", PARAM("stop_reference_advanced"), C("displacement_origin")],
                     FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                     FEAT("offset", price=BIND("array", "low" if d == "bullish" else "high"),
                          ticks=PARAM("stop_buffer_ticks"), direction=beyond)]
    else:                                                     # D
        setup = [
            node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
                 ["ADV-M05-C06", "INT-M04-C09", "ADV-M02-C06"], ["P-FVG-01", "P-RANGE-01"],
                 ["and", ["exists", htf_fvg],
                  ["==", FEAT("pd_location", tf="htf", price=FEAT("midpoint", zone=htf_fvg)), C(half)],
                  ["<=", BAR(ex, "low"), ["field", htf_fvg, "high"]] if d == "bullish"
                  else [">=", BAR(ex, "high"), ["field", htf_fvg, "low"]]],
                 emits={"htf_array": htf_fvg}),
            node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
                 ["INT-M08-R04", "ADV-M11-S04", "BEG-M03-R02"],
                 ["P-LIQ-02", "P-DISP-01", "P-MSS-01"],
                 ["and", ["==", raid, C("raid")],
                  FEAT("displacement", tf=ex, at_index=-1, direction=d),
                  FEAT("mss", tf=ex, at_index=-1, direction=d)],
                 emits={"raid_index": _sweep_of(ex, origin_side, kinds, "sweep_index"),
                        "raid_extreme": _sweep_of(ex, origin_side, kinds, "extreme"),
                        "displacement_index": FEAT("latest_index", tf=ex)}),
            node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
                 ["INT-M04-R05", "ADV-M09-C06", "ADV-M16-R03"], ["P-FVG-01"],
                 ["and", ["exists", ltf_fvg], ["overlaps", ltf_fvg, BIND("htf_array")]],
                 emits={"array": ltf_fvg}),
        ]
        zone_expr = BIND("array", "ce")
        stop_expr = ["if", ["==", PARAM("stop_scope"), C("ltf_tight")],
                     FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                     FEAT("offset", price=BIND("htf_array", "low" if d == "bullish" else "high"),
                          ticks=PARAM("stop_buffer_ticks"), direction=beyond)]

    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["ADV-M16-R03", "ADV-M05-C03", "INT-M04-R02"], ["P-FVG-01", "P-FIB-01"],
                      zone_expr, emits={"entry_zone": C("$value")})
    reach = (["<=", BAR(ex, "low"), BIND("array", "high")] if d == "bullish"
             else [">=", BAR(ex, "high"), BIND("array", "low")])
    ntrig = len(s["entry"]["trigger_options"])
    triggers = [node(f"{x}.entry.trigger.confirmation", "event",
                     src(sid, "entry.trigger_options", 0),
                     ["ADV-M16-R02", "ADV-M16-NT01", "ADV-M16-R08"], ["P-MSS-01", "P-GATE-01"],
                     ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
                      FEAT("mss", tf=ex, at_index=-1, direction=d), in_kz],
                     trigger_id="ltf_confirmation", fill={"mode": "market_on_close"})]
    if ntrig == 2:
        triggers.append(node(f"{x}.entry.gate", "event", src(sid, "entry.trigger_options", 1),
                             ["ADV-M16-R08", "ADV-M11-R01"], ["P-GATE-01"],
                             ["and", reach, checklist,
                              FEAT("mss", tf=ex, at_index=-1, direction=d)],
                             trigger_id="pre_entry_checklist",
                             fill={"mode": "market_on_close"},
                             compilation_note="The second trigger option is the pre-entry checklist "
                                              "gate; it adds no signal of its own, so it is compiled "
                                              "as the same confirmation entry with the checklist "
                                              "re-asserted."))
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["ADV-M16-R04", "ADV-M11-S02" if variation == "B" else "ADV-M11-S01",
                 "INT-M12-R02"], ["P-STOP-01"], stop_expr, execution_mode="close")
    invalidation = [node(f"{x}.inval.narrative", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["ADV-M11-R03", "ADV-M10-R05", "ADV-M12-R03", "INT-M08-R05"],
                         ["P-BIAS-02"], ["!=", bias, C(d)])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["ADV-M16-R05", "ADV-M16-R06", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             DOL(d, "irl", "htf", field="price"),
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["ADV-M16-R05", "ADV-M16-R06"], ["P-TARGET-01", "P-DOL-01"],
             DOL(d, "erl", "htf", field="price"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[0]),
                 ["ADV-M17-R02", "ADV-M17-R03", "ADV-M17-R04"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": ex, "direction": d, "po3_tf": ex}
    nt_nodes, nt_records, nt_unsup = nt_block(
        sid, info, ["ADV-M10-NT01", "ADV-M02-NT01", "ADV-M17-NT02", "ADV-M06-NT02"])
    unsup = list(nt_unsup) + list(pre_unsup)
    if variation == "B":
        unsup.append(unsupported(
            f"U-{x}-QUALITY", sid, src(sid, "context", "other"),
            "'high-quality' grading of the violated order block", "UNSUPPORTED_SUBJECTIVE",
            "The five quality filters of P-OB-01 are named but never weighted or thresholded, so "
            "'was itself high-quality' has no computable form. The compiled node applies only the "
            "observable Breaker test the source does define.",
            ["INT-M05-R03", "BEG-M06-C01", "P-OB-01"], False,
            "Stratify results by how many of the five named filters the block satisfied."))
        unsup[-1]["effect_if_unenforced"] = (
            "Breakers formed from low-quality order blocks are included; the population is broader "
            "than the specification intends.")
    if variation == "C":
        unsup.append(unsupported(
            "U-IFVG-HOLD", sid, src(sid, "setup_sequence", 2),
            "'demonstrably holding' after inversion", "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
            "The source requires the inverted gap to have been retested and to have held, but "
            "gives no price test for holding, and the specification itself records the definition "
            "as unspecified. The engine will not invent one.",
            ["ADV-M06-R03", "INT-M04-AMB01"], True,
            "Record an operationalisation for U-IFVG-HOLD and set inversion_hold_definition."))
        unsup.append(unsupported(
            f"U-{x}-STOP", sid, src(sid, "stop_invalidation", "trade_level"),
            "trade-level invalidation for this variation",
            "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
            "The source variation does not state a stop. The two general options it does document "
            "(far side of the entry array, displacement origin) are compiled behind a frozen "
            "choice; neither is preferred here.",
            ["ADV-M11-S03", "ADV-M12-S03", "ADV-M16-R04"], False,
            "Set stop_reference_advanced and report it as a research parameter."))
    if variation == "D":
        unsup.append(unsupported(
            f"U-{x}-STOPSCOPE", sid, src(sid, "stop_invalidation", "trade_level"),
            "trade-level invalidation scope (lower-timeframe tight vs higher-timeframe wide)",
            "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
            "The source documents both scopes without resolving them; the specification records "
            "the choice as something the researcher must freeze.",
            ["INT-M08-EX01", "ADV-M05-C10", "ADV-M16-R04"], False,
            "Set stop_scope and report it as a research parameter."))

    uncon = []
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    names = list(CORE) + ["fib_anchor", "ltf_confirmation_signal", "authorised_kill_zone_ET",
                          "decisive_close_definition", "max_daily_risk", "daily_loss_limit",
                          "rr_minimum", "daily_bias_method", "daily_open_definition"]
    names += {"A": ["stop_reference_advanced"],
              "B": ["stop_reference_breaker", "breaker_test"],
              "C": ["stop_reference_advanced", "inversion_hold_definition"],
              "D": ["stop_scope"]}[variation]
    if ntrig == 2:
        names.append("entry_trigger")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly", "monthly"], warmup=1000),
                    params(*names), blocks, unsup, uncon, nt_records, prim)


# ---------------------------------------------------------------------------
# family 13 — London-Open-conditioned buy/sell models (S19, S20)
# ---------------------------------------------------------------------------
def build_lokz(sid):
    s = SPEC[sid]
    d = "bullish" if s["direction"] == "long" else "bearish"
    o, half, beyond = OPP[d], HALF[d], BEYOND[d]
    origin_side, tgt_side = SIDE_OF[d], TARGET_SIDE[d]
    code = POOL_SIDE_CODE[origin_side]
    x = sid[:3]
    prim = ["P-BIAS-02", "P-BIAS-03", "P-DOL-01", "P-TIME-01", "P-TIME-02", "P-PO3-01",
            "P-LIQ-01", "P-LIQ-02", "P-DISP-01", "P-MSS-01", "P-FVG-01", "P-OB-01",
            "P-FIB-01", "P-RANGE-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("weekly and daily bias, range and draw on liquidity", ["1d", "1w"],
               ["INT-M11-R01", "ADV-M10-R03"], min_history=150),
        ltf_structure=tf("Asian range, sweep, MSS and the London-created array", ["5m", "15m"],
                         ["BEG-M11-S01", "INT-M09-R02"], min_history=1000),
        ltf_confirmation=tf("optional one-minute entry trigger", ["1m"],
                            ["BEG-M11-S01"], optional=True, min_history=1000),
    )
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    ar = lambda f: FEAT("session_range", tf="ltf_structure", window_param="asian_window_ET", field=f)
    asian_level = ar("low" if d == "bullish" else "high")
    sw = lambda f: FEAT("sweep", tf="ltf_structure", level=asian_level, side=code,
                        since_index=ar("end_index"), field=f)
    fvg = FEAT("fvg", tf="ltf_structure", direction=d, since_index=BIND("sweep_index"), select="latest")
    ob = FEAT("order_block", tf="ltf_structure", displacement_index=BIND("displacement_index"), direction=d)
    leg = lambda f: FEAT("displacement_leg", tf="ltf_structure",
                         at_index=BIND("displacement_index"), direction=d, field=f)
    fib = FEAT("fib_levels",
               origin=["if", ["==", PARAM("fib_anchor"), C("wick")], BIND("sweep_extreme"), leg("origin")],
               termination=leg("termination"))
    in_lokz = FEAT("in_session", window_param="london_open_kz_ET")

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["INT-M11-R01", "INT-M11-R02", "ADV-M10-R03", "BEG-M10-R02"],
             ["P-BIAS-02", "P-BIAS-03", "P-DOL-01"],
             ["and", ["==", bias, C(d)], ["==", PDLOC("htf", "ltf_structure"), C(half)],
              ["exists", DOL(d, "erl", "htf")]],
             emits={"dol_erl": DOL(d, "erl", "htf", field="price"),
                    "dol_irl": DOL(d, "irl", "htf", field="price")}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["INT-M10-EX01", "ADV-M14-C06", "INT-M06-R02"], ["P-RANGE-01"],
             ["==", PDLOC("htf", "ltf_structure"), C(half)]),
        node(f"{x}.ctx.asian", "predicate", src(sid, "context", "other"),
             ["BEG-M08-C03", "ADV-M07-R04"], ["P-TIME-02"],
             ["exists", FEAT("session_range", tf="ltf_structure", window_param="asian_window_ET")]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["ADV-M10-R03", "BEG-M10-R02", "BEG-M10-R03"], ["P-BIAS-03"],
             ["==", bias, C(d)]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M08-C03", "BEG-M11-EX01"], ["P-TIME-02", "P-LIQ-01"],
             ["and", ["exists", FEAT("session_range", tf="ltf_structure", window_param="asian_window_ET")],
              ["not", FEAT("in_session", window_param="asian_window_ET")]],
             emits={"asian_high": ar("high"), "asian_low": ar("low"),
                    "asian_end": ar("end_index"),
                    "secondary_pool": POOLS("ltf_structure", origin_side, ["prev_day"], "nearest",
                                            field="price")}),
        node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
             ["INT-M02-R02", "INT-M02-R04", "ADV-M03-R03"], ["P-DOL-01"],
             ["or", ["exists", DOL(d, "irl", "htf")], ["exists", DOL(d, "erl", "htf")]]),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["BEG-M08-R02", "BEG-M04-C08", "INT-M10-R01", "ADV-M07-R04"],
             ["P-TIME-01", "P-LIQ-02", "P-PO3-01"],
             ["and", in_lokz, ["==", sw("classification"), C("raid")]],
             emits={"sweep_extreme": sw("extreme"), "sweep_index": sw("sweep_index"),
                    "sweep_level": asian_level},
             also_covers=[{"block": "session", "index": "session"}]),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["BEG-M05-C01", "BEG-M05-R01"], ["P-DISP-01"],
             ["and", FEAT("displacement", tf="ltf_structure", at_index=-1, direction=d),
              [">", FEAT("latest_index", tf="ltf_structure"), BIND("sweep_index")]],
             emits={"displacement_index": FEAT("latest_index", tf="ltf_structure")}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["BEG-M03-R01", "BEG-M03-R02", "BEG-M11-S01"], ["P-MSS-01"],
             FEAT("mss", tf="ltf_structure", at_index=-1, direction=d)),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
             ["BEG-M08-R06"], ["P-LIQ-02"],
             ["not", FEAT("level_reclaimed", tf="ltf_structure", level=BIND("sweep_level"),
                          side=code, from_index=BIND("sweep_index"),
                          within_bars=PARAM("sweep_reclaim_bars"))]),
        node(f"{x}.setup.05", "event", src(sid, "setup_sequence", 4),
             ["BEG-M05-C04", "BEG-M06-C01", "BEG-M07-R01", "BEG-M07-R03"],
             ["P-FVG-01", "P-OB-01", "P-FIB-01"],
             ["and", ["exists", fvg],
              ["==", FEAT("pd_location", tf="htf", price=FEAT("midpoint", zone=fvg)), C(half)],
              FEAT("in_ote", fib=fib, zone=fvg)],
             emits={"array": fvg, "order_block": ob, "fib": fib}),
    ]
    reach = (["<=", BAR("ltf_structure", "low"), BIND("array", "high")] if d == "bullish"
             else [">=", BAR("ltf_structure", "high"), BIND("array", "low")])
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["BEG-M11-S01", "INT-M04-R02", "BEG-M07-C06"], ["P-FVG-01", "P-OB-01"],
                      ["if", ["==", PARAM("entry_level"), C("fvg_ce")], BIND("array", "ce"),
                       BIND("order_block", "high" if d == "bullish" else "low")],
                      emits={"entry_zone": C("$value")})
    ntrig = len(s["entry"]["trigger_options"])
    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["BEG-M11-S01", "INT-M09-EX01"], ["P-FVG-01"],
             ["and", reach, FEAT("in_ote", fib=BIND("fib"), price=BIND("entry_zone"))],
             trigger_id="limit_at_zone", fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event",
             src(sid, "entry.trigger_options", 0), ["BEG-M11-S01", "ADV-M16-R02"], ["P-MSS-01"],
             ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf_confirmation", at_index=-1, direction=d)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"}),
    ]
    if ntrig == 2:
        triggers.append(node(f"{x}.entry.window", "event", src(sid, "entry.trigger_options", 1),
                             ["INT-M09-EX01", "INT-M09-R06"], ["P-TIME-01"],
                             ["and", reach,
                              ["or", in_lokz, FEAT("in_session", window_param="new_york_open_kz_ET")]],
                             trigger_id="within_lokz_or_early_ny",
                             fill={"mode": "limit", "price": BIND("entry_zone")}))
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["BEG-M11-S01", "INT-M09-EX01", "INT-M12-EX01"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_lokz"), C("swept_asian_extreme")],
                 FEAT("offset", price=BIND("sweep_extreme"), ticks=PARAM("stop_buffer_ticks"),
                      direction=beyond),
                 ["if", ["==", PARAM("stop_reference_lokz"), C("displacement_origin")],
                  FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"), direction=beyond),
                  FEAT("offset",
                       price=FEAT("pick", values=[BIND("sweep_extreme"), leg("origin")],
                                  mode="min" if d == "bullish" else "max"),
                       ticks=PARAM("stop_buffer_ticks"), direction=beyond)]])
    invalidation = [
        node(f"{x}.inval.pattern", "predicate", src(sid, "stop_invalidation", "pattern_invalidation"),
             ["BEG-M11-NT01", "BEG-M12-NT01", "INT-M10-R05"], ["P-PO3-01"],
             ["==", PO3("ltf_structure"), C("failed")]),
        node(f"{x}.inval.narrative", "predicate", src(sid, "stop_invalidation", "narrative_level"),
             ["INT-M11-EX01", "INT-M11-R04"], ["P-BIAS-02"], ["!=", bias, C(d)]),
    ]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["INT-M12-EX01", "BEG-M08-C03", "ADV-M16-R06"], ["P-TARGET-01", "P-TIME-02"],
             BIND("asian_high" if d == "bullish" else "asian_low"),
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["INT-M09-EX01", "INT-M10-EX01", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             BIND("dol_erl"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[0]),
                 ["INT-M12-R01", "BEG-M13-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": "ltf_structure", "direction": d, "po3_tf": "ltf_structure"}
    nt_nodes, nt_records, nt_unsup = nt_block(
        sid, info, ["INT-M11-NT01", "BEG-M08-NT02", "INT-M09-NT01", "INT-M09-NT02", "INT-M10-NT01"])
    unsup = list(nt_unsup) + [
        unsupported("U-RECLAIM", sid, src(sid, "setup_sequence", 3),
                    "operational definition of 'reclaim'",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The Judas reclaim window is given in candles but no passage defines the price "
                    "test that constitutes a reclaim (CF-14).",
                    ["BEG-M08-R06"], True,
                    "Record an operationalisation for U-RECLAIM and set reclaim_definition."),
        unsupported(f"U-{x}-NARRATIVE", sid, src(sid, "prerequisites", 0),
                    "'daily conditional bias statement written pre-London'",
                    "UNSUPPORTED_PROCESS",
                    "Writing the statement is a process discipline. Its computable content — the "
                    "bias direction, the range half, the named draw and the condition that no "
                    "model is authorised until the London sweep, displacement and MSS have printed "
                    "— is compiled in the context block and in the setup sequence, which cannot "
                    "reach the entry step before those events latch.",
                    ["ADV-M10-R03", "INT-M11-EX01"], False,
                    "Record that the statement was written before the session."),
    ]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "ote_levels", "entry_level", "entry_trigger",
                  "ltf_confirmation_signal", "asian_window_ET", "london_open_kz_ET",
                  "new_york_open_kz_ET", "accumulation_window_ET", "reclaim_definition",
                  "stop_reference_lokz", "daily_bias_method", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=1000),
                    pars, blocks, unsup, uncon_empty(), nt_records, prim)


def uncon_empty():
    return []


# ---------------------------------------------------------------------------
# family 14 — New York continuation of the London array (S21)
# ---------------------------------------------------------------------------
def build_ny_continuation(sid="S21-NY-CONTINUATION-OF-LONDON"):
    s = SPEC[sid]
    x = "S21"
    prim = ["P-BIAS-02", "P-BIAS-03", "P-DOL-01", "P-TIME-01", "P-TIME-02", "P-LIQ-02",
            "P-DISP-01", "P-MSS-01", "P-FVG-01", "P-RANGE-01", "P-STOP-01", "P-TARGET-01",
            "P-RISK-01"]
    roles = tfmap(
        htf=tf("daily/weekly bias and the draw on liquidity", ["1d", "1w"],
               ["ADV-M14-R03", "INT-M09-R05"], min_history=150),
        array_timeframe=tf("the London leg and the array it left behind", ["15m", "5m"],
                           ["INT-M09-EX01"], min_history=1000),
        ltf_confirmation=tf("optional advanced confirmation entry", ["5m", "1m"],
                            ["ADV-M16-R02"], optional=True, min_history=1000),
    )
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    dirw = BIND("dir_word")
    ex = "array_timeframe"
    lon = lambda f: FEAT("session_range", tf=ex, window_param="london_open_kz_ET", field=f)
    fvg_b = FEAT("fvg", tf=ex, direction="bullish", select="latest")
    fvg_s = FEAT("fvg", tf=ex, direction="bearish", select="latest")
    long_case = ["==", bias, C("bullish")]
    array = ["if", long_case, fvg_b, fvg_s]

    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["ADV-M14-R03", "INT-M11-R01", "ADV-M03-R02"], ["P-BIAS-02", "P-DOL-01"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              ["exists", ["if", long_case, DOL("bullish", "erl", "htf"), DOL("bearish", "erl", "htf")]]],
             emits={"dir_word": bias,
                    "trade_direction": ["if", long_case, C("long"), C("short")],
                    "dol_erl": ["if", long_case, DOL("bullish", "erl", "htf", field="price"),
                                DOL("bearish", "erl", "htf", field="price")],
                    "dol_irl": ["if", long_case, DOL("bullish", "irl", "htf", field="price"),
                                DOL("bearish", "irl", "htf", field="price")]}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["ADV-M02-C06", "INT-M06-R02"], ["P-RANGE-01", "P-FVG-01"],
             ["==", FEAT("pd_location", tf="htf", price=FEAT("midpoint", zone=array)),
              ["if", long_case, C("discount"), C("premium")]]),
        node(f"{x}.ctx.london", "predicate", src(sid, "context", "other"),
             ["ADV-M14-R02", "ADV-M14-R03", "INT-M09-C06"], ["P-TIME-02", "P-FVG-01"],
             ["and", ["exists", FEAT("session_range", tf=ex, window_param="london_open_kz_ET")],
              ["exists", array]],
             emits={"array": array, "london_high": lon("high"), "london_low": lon("low")}),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["ADV-M14-R02", "ADV-M14-R03"], ["P-LIQ-02", "P-MSS-01"],
             ["==", ["if", long_case,
                     _sweep_of(ex, "sell", ["swing", "equal", "session_extreme"], "classification",
                               "asian_window_ET"),
                     _sweep_of(ex, "buy", ["swing", "equal", "session_extreme"], "classification",
                               "asian_window_ET")], C("raid")]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["ADV-M16-R03", "INT-M04-R03"], ["P-FVG-01", "P-FVG-02"],
             ["!=", FEAT("fvg_state", tf=ex, zone=BIND("array")), C("failed")]),
        node(f"{x}.pre.03", "predicate", src(sid, "prerequisites", 2),
             ["BEG-M08-R04", "INT-M09-R03"], ["P-TIME-01"],
             FEAT("in_session", window_param="new_york_open_kz_ET"),
             also_covers=[{"block": "session", "index": "session"}]),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["INT-M09-C06", "ADV-M06-C03", "ADV-M14-R03"], ["P-FVG-01"],
             ["if", ["==", dirw, C("bullish")],
              ["<=", BAR(ex, "low"), BIND("array", "high")],
              [">=", BAR(ex, "high"), BIND("array", "low")]]),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["ADV-M06-R02", "ADV-M04-R02"], ["P-DISP-01", "P-MSS-02"],
             ["not", ["and", FEAT("displacement", tf=ex, at_index=-1,
                                  direction=["if", ["==", dirw, C("bullish")], C("bearish"), C("bullish")]),
                      ["==", FEAT("mss_scope", tf=ex, at_index=-1, range_tf="htf"), C("external")]]]),
    ]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["ADV-M16-R03", "ADV-M06-C03"], ["P-FVG-01"], BIND("array", "ce"),
                      emits={"entry_zone": C("$value")})
    triggers = [
        node(f"{x}.entry.trigger.limit", "event", src(sid, "entry.trigger_options", 0),
             ["INT-M09-EX01", "INT-M04-R02"], ["P-FVG-01"],
             ["if", ["==", dirw, C("bullish")],
              ["<=", BAR(ex, "low"), BIND("entry_zone")],
              [">=", BAR(ex, "high"), BIND("entry_zone")]],
             trigger_id="limit_at_zone", fill={"mode": "limit", "price": BIND("entry_zone")}),
        node(f"{x}.entry.trigger.confirmation", "event", src(sid, "entry.trigger_options", 1),
             ["ADV-M16-R02", "ADV-M16-NT01"], ["P-MSS-01", "P-GATE-01"],
             ["and", ["if", ["==", dirw, C("bullish")],
                      ["<=", BAR(ex, "low"), BIND("array", "high")],
                      [">=", BAR(ex, "high"), BIND("array", "low")]],
              ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
              FEAT("mss", tf="ltf_confirmation", at_index=-1, direction=dirw)],
             trigger_id="ltf_confirmation", fill={"mode": "market_on_close"}),
    ]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["INT-M09-EX01", "ADV-M16-R04", "INT-M12-R02"], ["P-STOP-01"],
                ["if", ["==", dirw, C("bullish")],
                 FEAT("offset", price=BIND("array", "low"), ticks=PARAM("stop_buffer_ticks"),
                      direction="below"),
                 FEAT("offset", price=BIND("array", "high"), ticks=PARAM("stop_buffer_ticks"),
                      direction="above")],
                execution_mode="close")
    invalidation = [node(f"{x}.inval.narrative", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["ADV-M14-R03", "ADV-M04-R02"], ["P-BIAS-02", "P-MSS-02"],
                         ["!=", bias, dirw])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["INT-M09-EX01", "ADV-M16-R06"], ["P-TARGET-01", "P-DOL-01"],
             BIND("dol_irl"), allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["INT-M09-EX01", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             BIND("dol_erl"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", list(s["parameters"])[0]),
                 ["INT-M12-R01", "ADV-M17-R02"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": ex, "direction": "bullish", "po3_tf": ex}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["INT-M09-NT02", "ADV-M06-NT02"])
    unsup = list(nt_unsup) + [unsupported(
        "U-S21-01", sid, src(sid, "no_trade_conditions", "INT-M12-R05"),
        "high-impact scheduled news handling", "UNSUPPORTED_EXTERNAL_DATA",
        "The listed condition is a rule object, not a no-trade object, and it depends on an "
        "economic calendar the specification does not define or bound.",
        ["INT-M12-R05"], False,
        "Supply a calendar feed and stratify results by proximity to releases.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "entry_trigger", "ltf_confirmation_signal",
                  "asian_window_ET", "london_open_kz_ET", "new_york_open_kz_ET",
                  "decisive_close_definition", "daily_bias_method", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=1000),
                    pars, blocks, unsup, [], nt_records, prim)


# ---------------------------------------------------------------------------
# family 15 — Variation A with an SMT confirmation layer (S22) — blocked
# ---------------------------------------------------------------------------
def build_smt(sid="S22-ADV-A-SMT-CONFIRMED"):
    s = SPEC[sid]
    x = "S22"
    prim = ["P-SMT-01", "P-BIAS-02", "P-DOL-01", "P-RANGE-01", "P-LIQ-02", "P-DISP-01",
            "P-MSS-01", "P-FVG-01", "P-OB-01", "P-TIME-01", "P-GATE-01", "P-STOP-01",
            "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        htf=tf("single-instrument narrative and bias on the traded instrument", ["1d", "1w"],
               ["ADV-M13-R07"], min_history=150),
        smt_timeframe=tf("the timeframe on which the liquidity-extreme swings are compared; the "
                         "specification leaves it unspecified and implies the execution structure "
                         "timeframe", ["15m", "5m"], ["ADV-M13-R02"], min_history=1000),
    )
    ex = "smt_timeframe"
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    dirw = BIND("dir_word")
    long_case = ["==", bias, C("bullish")]
    kinds = ["swing", "equal", "prev_day"]
    raid = ["if", long_case, _sweep_of(ex, "sell", kinds, "classification"),
            _sweep_of(ex, "buy", kinds, "classification")]
    smt = FEAT("smt_divergence", tf=ex, side=["if", long_case, C("sell"), C("buy")],
               correlated="secondary")
    fvg = FEAT("fvg", tf=ex, direction=dirw, since_index=BIND("raid_index"), select="latest")
    ob = FEAT("order_block", tf=ex, displacement_index=BIND("displacement_index"), direction=dirw)
    leg = lambda f: FEAT("displacement_leg", tf=ex, at_index=BIND("displacement_index"),
                         direction=dirw, field=f)
    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["ADV-M13-R07", "ADV-M10-R01"], ["P-BIAS-02", "P-DOL-01"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              ["exists", ["if", long_case, DOL("bullish", "erl", "htf"), DOL("bearish", "erl", "htf")]]],
             emits={"dir_word": bias,
                    "trade_direction": ["if", long_case, C("long"), C("short")],
                    "dol_irl": ["if", long_case, DOL("bullish", "irl", "htf", field="price"),
                                DOL("bearish", "irl", "htf", field="price")],
                    "dol_erl": ["if", long_case, DOL("bullish", "erl", "htf", field="price"),
                                DOL("bearish", "erl", "htf", field="price")]}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["ADV-M02-C06", "ADV-M13-R04"], ["P-RANGE-01"],
             ["==", PDLOC("htf", ex), ["if", long_case, C("discount"), C("premium")]]),
        node(f"{x}.ctx.correlated", "predicate", src(sid, "context", "other"),
             ["ADV-M13-R01", "ADV-M13-C02"], ["P-SMT-01"],
             ["exists", STATE("correlated_instrument_view", name="secondary")]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["ADV-M11-R01", "ADV-M12-R01", "ADV-M16-R08"], ["P-GATE-01"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              ["==", PDLOC("htf", ex), ["if", long_case, C("discount"), C("premium")]],
              FEAT("in_session", window_param="authorised_kill_zone_ET")]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["ADV-M13-R01"], ["P-SMT-01"],
             ["exists", STATE("correlated_instrument_view", name="secondary")]),
        node(f"{x}.pre.session", "predicate", src(sid, "session", "session"),
             ["ADV-M13-R02", "ADV-M13-NT01", "ADV-M16-R07"], ["P-TIME-01", "P-SMT-01"],
             FEAT("in_session", window_param="authorised_kill_zone_ET")),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["ADV-M13-C03", "ADV-M13-R02", "ADV-M13-C05"], ["P-SMT-01", "P-LIQ-02"],
             ["and", ["==", raid, C("raid")], ["exists", smt]],
             emits={"smt": smt,
                    "raid_index": ["if", long_case,
                                   _sweep_of(ex, "sell", kinds, "sweep_index"),
                                   _sweep_of(ex, "buy", kinds, "sweep_index")],
                    "raid_extreme": ["if", long_case, _sweep_of(ex, "sell", kinds, "extreme"),
                                     _sweep_of(ex, "buy", kinds, "extreme")]}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["ADV-M13-R03"], ["P-SMT-01"],
             ["exists", ["field", BIND("smt"), "preferred_instrument"]],
             emits={"preferred_instrument": ["field", BIND("smt"), "preferred_instrument"]}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["ADV-M13-R04", "BEG-M03-R02", "BEG-M05-R01"], ["P-DISP-01", "P-MSS-01"],
             ["and", FEAT("displacement", tf=ex, at_index=-1, direction=dirw),
              FEAT("mss", tf=ex, at_index=-1, direction=dirw),
              [">", FEAT("latest_index", tf=ex), BIND("raid_index")]],
             emits={"displacement_index": FEAT("latest_index", tf=ex)}),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
             ["ADV-M13-R04", "ADV-M11-S01", "INT-M06-R03"], ["P-FVG-01", "P-OB-01", "P-RANGE-01"],
             ["and", ["exists", fvg],
              ["==", FEAT("pd_location", tf="htf", price=FEAT("midpoint", zone=fvg)),
               ["if", long_case, C("discount"), C("premium")]]],
             emits={"array": fvg, "order_block": ob}),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR(ex, "low"), BIND("array", "high")],
             [">=", BAR(ex, "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["ADV-M16-R03", "ADV-M11-S01"], ["P-FVG-01"], BIND("array", "ce"),
                      emits={"entry_zone": C("$value")})
    triggers = [node(f"{x}.entry.trigger", "event", src(sid, "entry.trigger_options", 0),
                     ["ADV-M16-R02", "ADV-M16-R08"], ["P-MSS-01", "P-GATE-01"],
                     ["and", reach, ["==", PARAM("ltf_confirmation_signal"), C("ltf_mss")],
                      FEAT("mss", tf=ex, at_index=-1, direction=dirw),
                      FEAT("in_session", window_param="authorised_kill_zone_ET")],
                     trigger_id="ltf_confirmation", fill={"mode": "market_on_close"})]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["ADV-M16-R04", "ADV-M11-S01"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_advanced"), C("displacement_origin")],
                 FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]),
                 FEAT("offset", price=["if", ["==", dirw, C("bullish")],
                                       BIND("array", "low"), BIND("array", "high")],
                      ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")])],
                execution_mode="close")
    invalidation = [node(f"{x}.inval.narrative", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["ADV-M13-R05", "ADV-M13-R07", "ADV-M11-R03"], ["P-BIAS-02"],
                         ["!=", bias, dirw])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["ADV-M16-R06"], ["P-TARGET-01", "P-DOL-01"], BIND("dol_irl"),
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["ADV-M16-R05"], ["P-TARGET-01", "P-DOL-01"], BIND("dol_erl"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", "size_adjustment_on_conflict"),
                 ["ADV-M17-R02", "ADV-M13-R07"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "htf", "ltf": ex, "direction": "bullish", "po3_tf": ex}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["ADV-M10-NT01"])
    unsup = list(nt_unsup) + [
        unsupported("U-SMT-CORR", sid, src(sid, "prerequisites", 1),
                    "'strong, stable current correlation' test and swing comparison window",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The specification requires verified correlation stability but records both "
                    "the threshold and the comparison window as unspecified. A correlation "
                    "computation is implemented, but its threshold and window must be frozen.",
                    ["ADV-M13-R01", "ADV-M13-R02"], True,
                    "Record an operationalisation for U-SMT-CORR and set smt_correlation_min and "
                    "smt_swing_comparison_window."),
        unsupported("U-S22-02", sid, src(sid, "setup_sequence", 1),
                    "'subject to which offers the cleaner array and better own-narrative alignment'",
                    "UNSUPPORTED_SUBJECTIVE",
                    "The mechanical half of instrument selection (prefer the instrument that held "
                    "the higher low, or printed the lower high) is compiled. Comparing array "
                    "cleanliness and narrative alignment across instruments has no price test.",
                    ["ADV-M13-R03"], False,
                    "Fix the traded instrument in advance and use SMT only as the on/off layer."),
        unsupported("U-S22-03", sid, src(sid, "parameters", "size_adjustment_on_conflict"),
                    "'smaller size' when SMT contradicts the bias",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The magnitude of the reduction is not stated.",
                    ["ADV-M13-R07"], False,
                    "Freeze a reduced risk_fraction for the contradicting-SMT stratum."),
        unsupported("U-S22-04", sid, src(sid, "context", "other"),
                    "second correlated instrument feed", "UNSUPPORTED_EXTERNAL_DATA",
                    "SMT is defined only across two instruments, so the run needs a second, "
                    "time-aligned bar feed. This is a data requirement rather than a rule gap and "
                    "is declared in data_requirements.correlated_instruments.",
                    ["ADV-M13-R01"], False,
                    "Supply the correlated instrument in MarketData.correlated['secondary']."),
    ]
    unsup[1]["effect_if_unenforced"] = (
        "The traded instrument is whichever the mechanical rule prefers, which may differ from the "
        "specification's discretionary choice.")
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "ltf_confirmation_signal", "authorised_kill_zone_ET",
                  "stop_reference_advanced", "decisive_close_definition", "smt_correlation_min",
                  "smt_swing_comparison_window", "daily_bias_method", "daily_open_definition")
    dq = datareq(roles, ["daily", "weekly"], warmup=1000, correlated=1)
    return assemble(sid, roles, dq, pars, blocks, unsup, [], nt_records, prim)


# ---------------------------------------------------------------------------
# family 16 — weekly Power-of-3 gate over daily models (S23) — blocked overlay
# ---------------------------------------------------------------------------
def build_weekly_gate(sid="S23-WEEKLY-PO3-GATED-DAILY"):
    s = SPEC[sid]
    x = "S23"
    prim = ["P-PO3-01", "P-BIAS-02", "P-RANGE-01", "P-DOL-01", "P-TIME-01", "P-GATE-01"]
    roles = tfmap(
        htf=tf("weekly phase, weekly range and weekly draw on liquidity", ["1w"],
               ["INT-M10-R02", "ADV-M08-R02"], min_history=60),
        execution=tf("the gated daily model's own execution timeframe", ["1d"],
                     ["ADV-M14-C06"], min_history=400),
    )
    bias = STATE("bias_state", tf="htf", method="structural", field="direction")
    long_case = ["==", bias, C("bullish")]
    context = [
        node(f"{x}.ctx.bias", "predicate", src(sid, "context", "htf_bias_required"),
             ["INT-M11-C01", "INT-M11-R01", "INT-M11-R05"], ["P-BIAS-02", "P-DOL-01"],
             ["and", ["in", bias, C(["bullish", "bearish"])],
              ["exists", ["if", long_case, DOL("bullish", "erl", "htf"),
                          DOL("bearish", "erl", "htf")]]],
             emits={"dir_word": bias,
                    "trade_direction": ["if", long_case, C("long"), C("short")]}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["ADV-M14-C06", "ADV-M02-R02"], ["P-RANGE-01"],
             ["==", PDLOC("htf", "execution"),
              ["if", long_case, C("discount"), C("premium")]]),
        node(f"{x}.ctx.phase", "predicate", src(sid, "context", "other"),
             ["INT-M10-C04", "ADV-M08-C03", "ADV-M14-C05"], ["P-PO3-01"],
             ["!=", PO3("execution", period="weekly"), C("undetermined")],
             emits={"weekly_phase": PO3("execution", period="weekly")}),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["ADV-M08-R02", "ADV-M14-C05"], ["P-PO3-01"],
             ["exists", FEAT("period_open", period="weekly", tf="execution")]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["ADV-M08-NT01", "INT-M10-R02"], ["P-PO3-01"],
             ["!=", PO3("execution", period="weekly"), C("undetermined")]),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["ADV-M08-R03", "INT-M10-R02", "INT-M10-R04"], ["P-PO3-01", "P-GATE-01"],
             ["and", ["==", PO3("execution", period="weekly"), C("distribution")],
              ["in", bias, C(["bullish", "bearish"])]]),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["INT-M10-R02", "ADV-M08-R03"], ["P-PO3-01"],
             ["!=", PO3("execution", period="weekly"), C("accumulation")]),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["ADV-M08-R03"], ["P-GATE-01"], C(True),
             compilation_note="'Then run the authorised daily model unchanged' is a delegation to "
                              "another compiled strategy, not a condition of this one; the gate "
                              "latches and hands over."),
    ]
    invalidation = [node(f"{x}.inval.weekly", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["INT-M11-R05", "ADV-M04-C09", "INT-M11-EX01"], ["P-BIAS-02"],
                         ["!=", bias, BIND("dir_word")])]
    info = {"htf": "htf", "ltf": "execution", "direction": "bullish", "po3_tf": "execution"}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["ADV-M08-NT01", "INT-M10-NT01", "ADV-M02-NT01"])
    unsup = list(nt_unsup) + [
        unsupported("U-S23-01", sid, src(sid, "prerequisites", 0),
                    "'early-week range', described only as 'often Monday'",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "The weekly accumulation range has no definition: the source says 'often "
                    "Monday' and simultaneously forbids rigid day-of-week rules (ADV-M08-NT01). "
                    "The compiled phase machine therefore has no weekly accumulation window to "
                    "measure from.",
                    ["INT-M10-R02", "ADV-M08-R02", "ADV-M08-NT01"], True,
                    "Record an operationalisation for U-S23-01 (an explicit early-week window or a "
                    "price-based accumulation-range rule) as a research parameter."),
        unsupported("U-S23-02", sid, src(sid, "entry.entry_zone", "entry_zone"),
                    "entry zone, trigger, stop and targets are delegated to the gated daily model",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "This specification is a gate, not a standalone trade model: every execution "
                    "element says 'as the gated daily model'. It compiles to a filter that must be "
                    "composed with S11, S15, S19, S20 or S21; it cannot be run alone.",
                    ["INT-M10-R02", "ADV-M08-R03"], True,
                    "Run it as an overlay: evaluate this document's gate and, when it passes, run "
                    "the chosen daily model's compiled document."),
        unsupported("U-S23-03", sid, src(sid, "parameters", "size_reduction_in_accumulation"),
                    "'reduced size' during weekly accumulation",
                    "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
                    "No reduction factor is given.",
                    ["INT-M10-R02"], False,
                    "Freeze a reduced risk_fraction for the accumulation stratum."),
    ]
    uncon = [
        unconstrained(src(sid, "entry.trigger_options", 0), "Delegated to the gated daily model; see U-S23-02."),
        unconstrained(src(sid, "stop_invalidation", "trade_level"), "Delegated to the gated daily model; see U-S23-02."),
        unconstrained(src(sid, "target", "primary"), "Delegated to the gated daily model; see U-S23-02."),
        unconstrained(src(sid, "target", "secondary"), "Delegated to the gated daily model; see U-S23-02."),
        unconstrained(src(sid, "session", "session"), "Delegated to the gated daily model."),
    ]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": None, "triggers": []}, "stop": None, "targets": [],
              "invalidation": invalidation, "no_trade": nt_nodes, "risk": []}
    pars = params("governing_swing_tier", "displacement_range_multiple", "displacement_lookback",
                  "displacement_body_ratio_min", "sweep_min_penetration", "sweep_reclaim_bars",
                  "equal_level_tolerance", "risk_fraction", "accumulation_window_ET",
                  "daily_open_definition")
    extra = {"overlay_of": ["S11-ADV-BUY-A-FVG-OTE", "S15-ADV-SELL-A-FVG-OTE",
                            "S19-BUY-LOKZ-ASIAN-SWEEP", "S20-SELL-LOKZ-ASIAN-SWEEP",
                            "S21-NY-CONTINUATION-OF-LONDON"]}
    return assemble(sid, roles, datareq(roles, ["weekly", "daily"], warmup=400),
                    pars, blocks, unsup, uncon, nt_records, prim, extra=extra)


# ---------------------------------------------------------------------------
# family 17 — session-level PO3 timed entry (S24) — blocked
# ---------------------------------------------------------------------------
def build_session_po3(sid="S24-SESSION-PO3-TIMED-ENTRY"):
    s = SPEC[sid]
    x = "S24"
    prim = ["P-PO3-01", "P-TIME-01", "P-LIQ-02", "P-DISP-01", "P-MSS-01", "P-FVG-01",
            "P-OB-01", "P-RANGE-01", "P-DOL-01", "P-STOP-01", "P-TARGET-01", "P-RISK-01"]
    roles = tfmap(
        daily=tf("daily Power-of-3 context and the daily draw on liquidity", ["1d"],
                 ["INT-M10-R03", "ADV-M08-C04"], min_history=150),
        session_structure=tf("session accumulation, manipulation and distribution; the "
                             "specification leaves the timeframe unspecified and implies 5m/1m",
                             ["5m", "1m"], ["INT-M10-R03"], min_history=1000),
    )
    ex = "session_structure"
    bias = STATE("bias_state", tf="daily", method="structural", field="direction")
    dirw = BIND("dir_word")
    long_case = ["==", bias, C("bullish")]
    kinds = ["swing", "session_extreme"]
    raid = ["if", long_case,
            _sweep_of(ex, "sell", kinds, "classification", "authorised_kill_zone_ET"),
            _sweep_of(ex, "buy", kinds, "classification", "authorised_kill_zone_ET")]
    fvg = FEAT("fvg", tf=ex, direction=dirw, since_index=BIND("session_manip_index"), select="latest")
    ob = FEAT("order_block", tf=ex, displacement_index=BIND("displacement_index"), direction=dirw)
    leg = lambda f: FEAT("displacement_leg", tf=ex, at_index=BIND("displacement_index"),
                         direction=dirw, field=f)
    context = [
        node(f"{x}.ctx.daily", "predicate", src(sid, "context", "htf_bias_required"),
             ["INT-M10-C03", "ADV-M08-C04", "INT-M10-R04"], ["P-PO3-01", "P-BIAS-02"],
             ["and", ["==", PO3(ex), C("distribution")], ["in", bias, C(["bullish", "bearish"])]],
             emits={"dir_word": bias,
                    "trade_direction": ["if", long_case, C("long"), C("short")]}),
        node(f"{x}.ctx.location", "predicate", src(sid, "context", "location"),
             ["ADV-M02-C06"], ["P-RANGE-01"],
             ["==", PDLOC("daily", ex), ["if", long_case, C("discount"), C("premium")]]),
        node(f"{x}.ctx.window", "predicate", src(sid, "context", "other"),
             ["INT-M10-C03", "ADV-M08-C04"], ["P-TIME-01"],
             FEAT("in_session", window_param="authorised_kill_zone_ET"),
             also_covers=[{"block": "session", "index": "session"}]),
    ]
    prereq = [
        node(f"{x}.pre.01", "predicate", src(sid, "prerequisites", 0),
             ["INT-M10-R01", "ADV-M08-R03"], ["P-PO3-01"], ["==", PO3(ex), C("distribution")]),
        node(f"{x}.pre.02", "predicate", src(sid, "prerequisites", 1),
             ["BEG-M08-R02", "BEG-M08-R04"], ["P-TIME-01"],
             FEAT("in_session", window_param="authorised_kill_zone_ET")),
    ]
    setup = [
        node(f"{x}.setup.01", "event", src(sid, "setup_sequence", 0),
             ["INT-M10-C03", "BEG-M09-C01"], ["P-PO3-01", "P-TIME-01"],
             ["exists", FEAT("session_range", tf=ex, window_param="authorised_kill_zone_ET")],
             emits={"session_high": FEAT("session_range", tf=ex,
                                         window_param="authorised_kill_zone_ET", field="high"),
                    "session_low": FEAT("session_range", tf=ex,
                                        window_param="authorised_kill_zone_ET", field="low")}),
        node(f"{x}.setup.02", "event", src(sid, "setup_sequence", 1),
             ["INT-M10-R03", "ADV-M08-C04", "BEG-M04-C08"], ["P-LIQ-02", "P-PO3-01"],
             ["==", raid, C("raid")],
             emits={"session_manip_index": ["if", long_case,
                                            _sweep_of(ex, "sell", kinds, "sweep_index", "authorised_kill_zone_ET"),
                                            _sweep_of(ex, "buy", kinds, "sweep_index", "authorised_kill_zone_ET")],
                    "session_manip_extreme": ["if", long_case,
                                              _sweep_of(ex, "sell", kinds, "extreme", "authorised_kill_zone_ET"),
                                              _sweep_of(ex, "buy", kinds, "extreme", "authorised_kill_zone_ET")]}),
        node(f"{x}.setup.03", "event", src(sid, "setup_sequence", 2),
             ["INT-M10-R03", "BEG-M05-R01", "BEG-M03-R02"], ["P-DISP-01", "P-MSS-01"],
             ["and", FEAT("displacement", tf=ex, at_index=-1, direction=dirw),
              FEAT("mss", tf=ex, at_index=-1, direction=dirw),
              [">", FEAT("latest_index", tf=ex), BIND("session_manip_index")]],
             emits={"displacement_index": FEAT("latest_index", tf=ex)}),
        node(f"{x}.setup.04", "event", src(sid, "setup_sequence", 3),
             ["INT-M10-R03", "BEG-M05-C04", "BEG-M06-C01"], ["P-FVG-01", "P-OB-01"],
             ["exists", fvg], emits={"array": fvg, "order_block": ob}),
    ]
    reach = ["if", ["==", dirw, C("bullish")],
             ["<=", BAR(ex, "low"), BIND("array", "high")],
             [">=", BAR(ex, "high"), BIND("array", "low")]]
    entry_zone = node(f"{x}.entry.zone", "selection", src(sid, "entry.entry_zone", "entry_zone"),
                      ["INT-M10-R03", "INT-M04-R02"], ["P-FVG-01"], BIND("array", "ce"),
                      emits={"entry_zone": C("$value")})
    triggers = [node(f"{x}.entry.trigger", "event", src(sid, "entry.trigger_options", 0),
                     ["ADV-M08-C04", "INT-M10-R03"], ["P-MSS-01"], reach,
                     trigger_id="after_session_mss",
                     fill={"mode": "limit", "price": BIND("entry_zone")})]
    stop = node(f"{x}.stop", "selection", src(sid, "stop_invalidation", "trade_level"),
                ["INT-M10-R03", "P-STOP-01" and "BEG-M09-S01"], ["P-STOP-01"],
                ["if", ["==", PARAM("stop_reference_po3"), C("manipulation_extreme")],
                 FEAT("offset", price=BIND("session_manip_extreme"),
                      ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")]),
                 FEAT("offset", price=leg("origin"), ticks=PARAM("stop_buffer_ticks"),
                      direction=["if", ["==", dirw, C("bullish")], C("below"), C("above")])])
    invalidation = [node(f"{x}.inval.daily", "predicate",
                         src(sid, "stop_invalidation", "narrative_level"),
                         ["INT-M10-R05", "ADV-M08-R05"], ["P-PO3-01"],
                         ["==", PO3(ex), C("failed")])]
    targets = [
        node(f"{x}.target.primary", "selection", src(sid, "target", "primary"),
             ["INT-M10-R03", "INT-M09-R05"], ["P-TARGET-01", "P-TIME-02"],
             ["if", ["==", dirw, C("bullish")], BIND("session_high"), BIND("session_low")],
             allocation={"param": "first_target_allocation"}),
        node(f"{x}.target.secondary", "selection", src(sid, "target", "secondary"),
             ["INT-M10-R01", "ADV-M03-R03"], ["P-TARGET-01", "P-DOL-01"],
             FEAT("dol", direction=dirw, scope="erl", tf="daily", field="price"), allocation=0.0),
    ]
    risk = [node(f"{x}.risk.size", "action", src(sid, "parameters", "session_range_definition"),
                 ["INT-M12-R01"], ["P-RISK-01"],
                 FEAT("position_size", entry=BIND("entry_price"), stop=BIND("stop_price")),
                 emits={"position_size": C("$value")})]
    info = {"htf": "daily", "ltf": ex, "direction": "bullish", "po3_tf": ex}
    nt_nodes, nt_records, nt_unsup = nt_block(sid, info, ["ADV-M08-NT01", "BEG-M09-NT01", "INT-M10-NT01"])
    unsup = list(nt_unsup) + [unsupported(
        "U-S24-01", sid, src(sid, "setup_sequence", 0),
        "'brief local range inside the window' — the session accumulation range",
        "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
        "The specification records session_range_definition as unspecified: how long the local "
        "range must build, and how tight it must be, is never stated. The compiled node uses the "
        "completed kill-zone window as the range, which is an operationalisation, not the source's "
        "own rule.",
        ["INT-M10-R03"], True,
        "Record an operationalisation for U-S24-01 fixing the session accumulation window and its "
        "tightness test.")]
    blocks = {"context": context, "prerequisites": prereq, "setup_sequence": setup,
              "entry": {"zone": entry_zone, "triggers": triggers}, "stop": stop,
              "targets": targets, "invalidation": invalidation, "no_trade": nt_nodes, "risk": risk}
    pars = params(*CORE, "fib_anchor", "authorised_kill_zone_ET", "accumulation_window_ET",
                  "stop_reference_po3", "daily_open_definition")
    return assemble(sid, roles, datareq(roles, ["daily", "weekly"], warmup=1000),
                    pars, blocks, unsup, [], nt_records, prim)


# ---------------------------------------------------------------------------
BUILDERS = {
    "S01-BUY-11STEP": lambda: build_eleven_step("S01-BUY-11STEP"),
    "S02-SELL-11STEP": lambda: build_eleven_step("S02-SELL-11STEP"),
    "S03-BULL-DISCOUNT-FW": lambda: build_framework("S03-BULL-DISCOUNT-FW"),
    "S04-BEAR-PREMIUM-FW": lambda: build_framework("S04-BEAR-PREMIUM-FW"),
    "S05-PO3-DAILY": build_po3_daily,
    "S06-JUDAS-LONDON": build_judas,
    "S07-NYKZ-SWEEP-SEQUENCE": build_nykz,
    "S08-LONDON-CLOSE-RETRACE": build_london_close,
    "S09-OTE-ENTRY-COMPONENT": build_ote_component,
    "S10-DAILY-SCALP": build_daily_scalp,
    "S11-ADV-BUY-A-FVG-OTE": lambda: build_adv("S11-ADV-BUY-A-FVG-OTE", "A"),
    "S12-ADV-BUY-B-BREAKER": lambda: build_adv("S12-ADV-BUY-B-BREAKER", "B"),
    "S13-ADV-BUY-C-IFVG": lambda: build_adv("S13-ADV-BUY-C-IFVG", "C"),
    "S14-ADV-BUY-D-HTF-ARRAY-LTF": lambda: build_adv("S14-ADV-BUY-D-HTF-ARRAY-LTF", "D"),
    "S15-ADV-SELL-A-FVG-OTE": lambda: build_adv("S15-ADV-SELL-A-FVG-OTE", "A"),
    "S16-ADV-SELL-B-BREAKER": lambda: build_adv("S16-ADV-SELL-B-BREAKER", "B"),
    "S17-ADV-SELL-C-IFVG": lambda: build_adv("S17-ADV-SELL-C-IFVG", "C"),
    "S18-ADV-SELL-D-HTF-ARRAY-LTF": lambda: build_adv("S18-ADV-SELL-D-HTF-ARRAY-LTF", "D"),
    "S19-BUY-LOKZ-ASIAN-SWEEP": lambda: build_lokz("S19-BUY-LOKZ-ASIAN-SWEEP"),
    "S20-SELL-LOKZ-ASIAN-SWEEP": lambda: build_lokz("S20-SELL-LOKZ-ASIAN-SWEEP"),
    "S21-NY-CONTINUATION-OF-LONDON": build_ny_continuation,
    "S22-ADV-A-SMT-CONFIRMED": build_smt,
    "S23-WEEKLY-PO3-GATED-DAILY": build_weekly_gate,
    "S24-SESSION-PO3-TIMED-ENTRY": build_session_po3,
}


def main():
    from strategy_compiler.engine.dsl import validate

    os.makedirs(OUT_DSL, exist_ok=True)
    docs, registry, tfreq, problems = {}, [], {}, []
    for sid in sorted(SPEC):
        if sid not in BUILDERS:
            problems.append(f"no builder for approved specification {sid}")
            continue
        doc = BUILDERS[sid]()
        validate(doc)
        cov = coverage(doc)
        if cov["missing_elements"] or cov["verbatim_errors"]:
            problems.append(f"{sid}: coverage {cov}")
        docs[sid] = doc
        registry.extend(doc["unsupported"])
        tfreq[sid] = {
            "execution_timeframe_role": min(
                (r for r in doc["timeframes"] if not doc["timeframes"][r].get("optional")),
                key=lambda r: doc["timeframes"][r]["candidates"][-1]),
            "roles": doc["timeframes"],
            "data_requirements": doc["data_requirements"],
        }
        with open(os.path.join(OUT_DSL, f"{sid}.json"), "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=False)
            fh.write("\n")

    by_reason: Dict[str, int] = {}
    for u in registry:
        by_reason[u["reason_code"]] = by_reason.get(u["reason_code"], 0) + 1
    with open(os.path.join(PKG, "dsl", "unsupported_registry.json"), "w") as fh:
        json.dump({
            "_meta": {
                "title": "Unsupported and gap registry — conditions that do not map to a "
                         "deterministic computational operation",
                "policy": "Identified, marked, never silently approximated. An item with "
                          "blocks_execution=true refuses to run until an explicit "
                          "operationalisation is recorded in the run configuration and copied into "
                          "the run manifest (ADV-M18-R01, ADV-M18-C03).",
                "execution_model_parameters": [
                    {"name": "setup_expiry_bars",
                     "why": "No specification states how long a partially formed setup stays "
                            "live. Without a bound, a latched liquidity event that never produced "
                            "displacement would block the machine for the rest of the sample.",
                     "status": "execution-model research parameter, not a rule from the source "
                               "(ADV-M18-C03); required, no default; recorded in the run manifest."},
                    {"name": "intrabar_policy",
                     "why": "When a bar's range contains both the stop and a target, the source "
                            "cannot say which came first.",
                     "status": "declared choice ('stop_first' or 'target_first'), recorded in the "
                               "run manifest."},
                    {"name": "latch supersession",
                     "why": "A pending setup is abandoned when the market prints a different first "
                            "event (a different origin pool, or a different sweep of it).",
                     "status": "fixed execution-model rule, documented in DSL_SPEC.md; it removes "
                               "no condition the source states."},
                ],
                "counts_by_reason_code": dict(sorted(by_reason.items())),
                "blocking_items": sorted({u["item_id"] for u in registry if u["blocks_execution"]}),
                "blocked_strategies": sorted(s for s, d in docs.items() if d["executability"] == "blocked"),
            },
            "items": registry,
        }, fh, indent=2)
        fh.write("\n")

    with open(os.path.join(PKG, "requirements", "timeframe_requirements.json"), "w") as fh:
        json.dump({
            "_meta": {
                "title": "Required Timeframe Data",
                "rule": "The execution timeframe is the fastest non-optional role; it is the only "
                        "clock on which fills occur. Every role must be bound to a concrete "
                        "timeframe in the frozen configuration, and every bar must carry a "
                        "timezone-aware close_time because all session windows are anchored to New "
                        "York time (BEG-M08-R05).",
                "timeframe_identifiers": ["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"],
            },
            "strategies": tfreq,
        }, fh, indent=2)
        fh.write("\n")

    print(f"compiled {len(docs)} strategies -> {OUT_DSL}")
    print(f"unsupported registry: {len(registry)} items, "
          f"{len([u for u in registry if u['blocks_execution']])} blocking")
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
