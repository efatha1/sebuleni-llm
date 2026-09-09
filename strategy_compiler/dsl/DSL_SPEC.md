# Canonical Strategy DSL — Specification v1.0.0

**Scope.** This DSL is a *translation target*. It expresses the approved strategy
specifications in `strategy_reearcher/catalog/strategies.json` as deterministic computational
operations. It adds no concepts, filters, indicators, entry conditions, exits or risk rules.

Every DSL node carries the verbatim source text it was compiled from
(`source.text`) and the knowledge-base object ids that authorise it (`kb_refs`).
A source element that cannot be mapped to a deterministic operation is **not** compiled into
an expression; it is emitted into `unsupported[]` with a reason code, and it never silently
becomes an approximation.

---

## 1. Document structure

```jsonc
{
  "dsl_version": "1.0.0",
  "strategy_id": "S01-BUY-11STEP",
  "name": "...",
  "kind": "base_model | variant | component",
  "parent_strategy_id": "S01-BUY-11STEP" | null,
  "direction": "long | short | reversal_bidirectional | either",
  "provenance": {
    "spec_file": "strategy_reearcher/catalog/strategies.json",
    "spec_strategy_id": "S01-BUY-11STEP",
    "kb_source_strategy_ids": ["BEG-M11-S01"],
    "primitives": ["P-LIQ-02", "P-DISP-01", ...]
  },
  "timeframes":   { "<role>": { ... } },       // see §5
  "data_requirements": { ... },                // see §5
  "parameters":   [ Parameter, ... ],          // see §4
  "features":     ["<feature_id>", ...],       // see §6 — closed set
  "market_state": ["<state_id>", ...],         // see §7 — closed set
  "blocks": {
    "context":         [Node, ...],
    "prerequisites":   [Node, ...],
    "setup_sequence":  [Node, ...],            // ordered; each node is an event
    "entry":           { "zone": Node, "triggers": [Node, ...] },
    "stop":            Node,
    "targets":         [Node, ...],
    "invalidation":    [Node, ...],
    "no_trade":        [Node, ...],
    "risk":            [Node, ...]
  },
  "unsupported":   [ UnsupportedItem, ... ],   // see §8
  "unconstrained": [ { "source": {...}, "note": "..." } ],  // see §8.1
  "executability": "executable | blocked",
  "blocking_items": ["U-S08-01", ...]
}
```

`executability` is `blocked` if and only if at least one `UnsupportedItem` has
`blocks_execution: true`. A blocked strategy still compiles, still validates, and still
publishes its feature/timeframe/market-state requirements — it simply refuses to run until the
listed items are given an explicit, recorded operationalisation.

---

## 2. Node

```jsonc
{
  "node_id": "S01.setup.03",
  "kind": "predicate | event | selection | action",
  "source": { "block": "setup_sequence", "index": 0, "text": "Step 3 — Liquidity sweep: ..." },
  "kb_refs": ["BEG-M11-S01"],
  "primitives": ["P-LIQ-02"],
  "expr": Expr,
  "emits": { "sweep": Expr, ... },     // bindings published when the node succeeds;
                                       // the literal ["const","$value"] means "this node's own value"
  "ordering": { "within_bars": {"param": "sweep_reclaim_bars"} } | null,
  "gate": true | false,                // context/prerequisite nodes only; see below
  "also_covers": [ {"block": "...", "key|index": ...} ],   // extra specification elements this node satisfies
  "trigger_id": "limit_at_zone",       // entry triggers only
  "fill": { "mode": "limit", "price": Expr } | { "mode": "market_on_close" },   // entry triggers only
  "allocation": 0.5 | {"param": "..."} // target nodes only
}
```

* `predicate` — a boolean condition evaluated at a bar; carries no state.
* `event`     — a predicate that, when first true, is *latched* with its bar index and publishes
                `emits` bindings. Setup sequences are ordered chains of events.
* `selection` — computes and publishes a value (a price level, a pool, an array) without a
                boolean gate. Used for entry zones, stops and targets.
* `action`    — a sizing/management instruction (risk block only).

`gate: false` marks a context/prerequisite node that the specification states as a quality
preference ("setup considered stronger when ...", "preferably ...") rather than a requirement.
Such a node is evaluated and its bindings published, but it never vetoes a setup: promoting a
preference to a filter would change the trading logic.

Latching is what makes the sequence deterministic: an event's bar index is fixed at the bar that
first satisfies it and is never revised by later data.

---

## 3. Expression grammar

Expressions are prefix lists. This is the complete grammar; there are no other forms.

```
Expr := Const | Ref | Call | Logic | Compare

Const   := ["const", <json scalar>]
Ref     := ["param",   "<parameter name>"]
         | ["binding", "<binding name>", "<field>"]
Call    := ["feature", "<feature_id>", {kwargs}]
         | ["state",   "<state_id>",   {kwargs}]
Logic   := ["and", Expr, ...] | ["or", Expr, ...] | ["not", Expr]
Compare := ["==", Expr, Expr] | ["!=", Expr, Expr]
         | ["<",  Expr, Expr] | ["<=", Expr, Expr]
         | [">",  Expr, Expr] | [">=", Expr, Expr]
         | ["between", Expr, Expr, Expr]        // lo <= x <= hi, inclusive
         | ["in", Expr, ["const", [ ... ]]]
         | ["exists", Expr]                     // value is not None
         | ["overlaps", Expr, Expr]             // two [lo,hi] zones intersect
         | ["if", Expr, Expr, Expr]             // selects between two documented alternatives
```

`if` exists only to encode a *frozen choice between alternatives the source itself documents*
(for example the Fibonacci anchor conflict CF-01). Its condition is always a comparison against
a `frozen_choice` parameter, never against market data.

`kwargs` values are themselves `Expr` or JSON scalars. Timeframe arguments are given as
timeframe **roles** (`"htf"`, `"ltf_structure"`, ...), never as hard-coded bar sizes; the role is
resolved through `timeframes` at run time.

Evaluation is total and deterministic: every operator is a pure function of
(visible market data, frozen parameters, latched bindings). Missing values propagate as `None`
and make comparisons `False`; `["exists", ...]` is the only way to test for presence.

---

## 4. Parameter

```jsonc
{
  "name": "displacement_body_ratio_min",
  "binding": "literal | frozen_required | frozen_choice",
  "value": 0.62,                       // literal only
  "choices": [[ "02:00", "05:00" ], [ "02:00", "04:00" ]],   // frozen_choice only
  "kb_status": "specified | specified_approx | range_given | alternatives_documented | heuristic_unfixed | unspecified",
  "kb_value": "~60-70% cited by secondary tools; not fixed by the book",
  "source": ["BEG-M05-C01", "BEG-M05-AMB01"],
  "register_id": "displacement_body_to_range_min"      // key in parameter_register.json
}
```

* `literal` — the knowledge base fixes the value. It is inlined and is not configurable.
* `frozen_required` — the knowledge base gives no value. The run configuration **must** supply
  one; there is no default anywhere in the engine. A missing value raises `UnspecifiedParameter`.
* `frozen_choice` — the knowledge base documents two or more alternatives. The configuration must
  select one of `choices`; selecting a value outside `choices` is rejected.

This mirrors `strategy_reearcher/engine/ict_primitives.FrozenParams`, which already refuses to
label anything without a frozen value, and `research/research_config_template.json`.

---

## 5. Timeframes and data requirements

```jsonc
"timeframes": {
  "htf":            { "purpose": "bias / structure", "candidates": ["1D", "4H"], "kb_status": "specified_examples", "source": ["BEG-M11-S01"] },
  "ltf_structure":  { "purpose": "MSS, FVG/OB",      "candidates": ["15m", "5m"], ... },
  "ltf_confirmation": { "purpose": "entry trigger",  "candidates": ["1m"], "optional": true, ... }
},
"data_requirements": {
  "instrument": "primary",
  "correlated_instruments": 0,                 // 1 for the SMT variant
  "bars": { "htf": {"min_history": 60}, ... },
  "timezone": "America/New_York",              // BEG-M08-R05
  "session_anchored": true,
  "requires_period_opens": ["daily", "weekly", "monthly"],
  "external_data": []                          // e.g. ["scheduled_news_calendar"] — see §8
}
```

The **execution timeframe** is the lowest declared role; it is the bar clock the backtester
iterates and the only clock on which fills occur.

---

## 6. Feature identifiers (closed set)

A compiled expression may only call features in `requirements/feature_registry.json`. Each
feature is a pure function of the visible bar window and frozen parameters, implemented in
`engine/features.py`, and maps 1:1 onto a primitive in `catalog/primitives.json`.

Adding a feature is a change to the knowledge-base-derived primitive library, not a compilation
decision, and is out of scope for this agent.

## 7. Market-state identifiers (closed set)

Market state is derived, not stored: `["state", id, kwargs]` recomputes from the visible window
at every call. This removes any possibility of state leaking backwards or forwards and makes a
run reproducible from `(data, config)` alone. Definitions live in
`requirements/market_state_requirements.json` and `engine/market_state.py`.

---

## 8. Unsupported items

```jsonc
{
  "item_id": "U-S06-01",
  "strategy_id": "S06-JUDAS-LONDON",
  "source": { "block": "setup_sequence", "index": 3, "text": "Reclaim test: confirm price does not reclaim the swept level ..." },
  "element": "operational definition of 'reclaim'",
  "reason_code": "GAP_REQUIRES_FROZEN_OPERATIONALISATION",
  "explanation": "The knowledge base counts candles for the reclaim window but never defines the price test that constitutes a reclaim (CF-14, BEG-M08-R06).",
  "kb_refs": ["BEG-M08-R06"],
  "blocks_execution": true,
  "resolution": "Supply reclaim_definition in the frozen configuration; it is a research parameter (ADV-M18-C03), not doctrine (ADV-M18-R01)."
}
```

### Reason codes

| Code | Meaning | Blocks execution |
|---|---|---|
| `GAP_REQUIRES_FROZEN_OPERATIONALISATION` | The source names the condition but supplies no computational test. A frozen choice makes it computable; the engine will not invent one. | yes, until frozen |
| `UNSUPPORTED_SUBJECTIVE` | A gestalt/aesthetic judgment ("obvious at a glance", "clean array", "cleaner array and better narrative alignment"). No price-data operation is equivalent. | yes if it gates entry; no if it only grades quality |
| `UNSUPPORTED_PROCESS` | A human process/discipline instruction (write the narrative pre-session, journaling). Not a market condition. | no |
| `UNSUPPORTED_EXTERNAL_DATA` | Requires a non-price data source the specification does not define (economic calendar). | yes if it gates entry |

### 8.1 Unconstrained elements

A specification element that states *no* constraint ("session: unspecified", "not restricted in
the generic statement") is neither compiled nor unsupported — there is nothing to represent. It
is listed in `unconstrained[]` so that the coverage audit can still account for every element of
the source specification.

### 8.2 Coverage audit

`tools/audit_translation.py` asserts that every element of every approved specification —
each `context` key, each `prerequisites` entry, each `setup_sequence` entry, the entry zone,
each `trigger_options` entry, each `stop_invalidation` key, each `target` key and `session` — is
accounted for by exactly one of: a compiled node (via `source` or `also_covers`), an
`unsupported` item, or an `unconstrained` entry. Nothing may be dropped, and no compiled node may
exist without a source element behind it.

The engine enforces this: `engine/runtime.py` raises `UnsupportedCondition` if a blocked
strategy is executed without every blocking item having an explicit entry in the run
configuration's `operationalisations` map, and every such entry is copied into the run manifest
so results can never be reported as the specification's own behaviour.

---

## 8.3 Execution-model parameters

Three things a backtester must decide are decided by *no* strategy specification. They are not
compiled as strategy logic; they are run-configuration fields, they have no defaults, and they are
recorded in the run manifest so results can never be attributed to the source:

| Field | Why it exists |
|---|---|
| `setup_expiry_bars` | No specification states how long a partially formed setup stays live. Without a bound, a latched liquidity event that never produced displacement blocks the machine for the rest of the sample. Measured from the previously latched event. A node may override it with `ordering.within_bars`. |
| `intrabar_policy` | When one bar's range contains both the stop and a target, no source can say which was reached first. |
| latch supersession | A pending setup is abandoned as soon as the first event re-evaluates to a *different* event (a different origin pool, or a different sweep of it). This is a fixed engine rule rather than a parameter; it removes no condition the source states. |

## 9. Determinism contract

For a fixed `(compiled DSL, bar data, instrument configuration, frozen configuration)` the
backtester produces byte-identical results. Guarantees:

1. No wall-clock, no RNG, no hashing of object identity, no iteration over unordered containers.
2. All feature values are pure functions of the bar window visible at the decision bar; the
   window is `close_time <= decision bar close_time` on every timeframe.
3. Intrabar ambiguity is resolved by one declared rule (`stop_first` or `target_first`,
   configuration field `intrabar_policy`) rather than by data order.
4. Every run emits a manifest containing the SHA-256 of the compiled DSL, the frozen
   configuration, the instrument configuration and the bar data, plus the SHA-256 of the trade
   list. `tests/test_determinism.py` asserts two independent runs agree on all five digests.
