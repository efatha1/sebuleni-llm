# Strategy Compilation — ICT Strategy Catalog → canonical DSL and executable backtest

**Input (approved specifications):** `strategy_reearcher/catalog/strategies.json` — 24 strategy
specifications, composed from the 26 detection primitives in `catalog/primitives.json`, all traced
to the `sebuleni-llm` knowledge base.

**Output:** a canonical Strategy DSL document per strategy, the feature / timeframe /
market-state requirements those documents imply, a deterministic backtesting engine that executes
them, a registry of everything that could **not** be mapped to a computation, and a validation
suite that proves the translation changed nothing.

This layer performs **translation only**. It adds no concept, filter, indicator, entry condition,
exit or risk rule. The property is machine-checked, not asserted — see §6.

---

## 1. Layout

```
strategy_compiler/
  dsl/
    DSL_SPEC.md                     canonical DSL grammar and semantics (v1.0.0)
    compiled/<STRATEGY_ID>.json     24 compiled strategy documents
    unsupported_registry.json       58 items that do not map to a deterministic operation
  requirements/
    feature_registry.json           35 required features (closed set, 1:1 with the primitives)
    market_state_requirements.json  11 required market-state calculations
    timeframe_requirements.json     per-strategy timeframe and data requirements
  engine/
    data.py          bars, multi-timeframe container, look-ahead-controlled View
    freeze.py        frozen run configuration (no defaults anywhere)
    market_state.py  the 11 market-state calculations
    features.py      the 35 features, delegating to the reference primitive library
    runtime.py       expression evaluator and node semantics
    dsl.py           load / validate / prepare
    backtest.py      deterministic execution engine
  tests/             41 validation tests  (python3 -m strategy_compiler.tests.run_all)
  tools/
    compile_strategies.py   regenerates dsl/compiled/ from the approved specifications
    audit_translation.py    proves nothing was added or dropped
  configs/
    example_frozen_config.S01.json
```

Run everything:

```bash
cd <repo root>
python3 -m strategy_compiler.tools.compile_strategies    # regenerate the compiled DSL
python3 -m strategy_compiler.tools.audit_translation     # translation audit
python3 -m strategy_compiler.tests.run_all               # 41 validation tests
```

---

## 2. Canonical Strategy DSL

`dsl/DSL_SPEC.md` defines it in full. In short:

* A strategy is a document of typed **nodes** grouped into `context`, `prerequisites`,
  `setup_sequence`, `entry`, `stop`, `targets`, `invalidation`, `no_trade` and `risk`.
* Each node carries the **verbatim source text** it was compiled from, the knowledge-base object
  ids that authorise it, and the primitives it uses.
* Node logic is a small prefix expression language whose only leaves are `feature`, `state`,
  `param`, `binding` and `const`. There is no escape hatch: an expression cannot call arbitrary
  code, so a strategy cannot smuggle in a rule the registries do not contain.
* Where the source documents **two** ways to operationalise the same component (the Fibonacci
  anchor, the kill-zone bounds, the stop reference, the entry trigger, the Breaker test…), both
  are compiled behind a `frozen_choice` parameter and an `["if", ...]` selector. Neither is
  preferred, and choosing a value outside the documented menu is rejected.
* `gate: false` marks a node the source states as a *preference* ("setup considered stronger
  when…", "preferably…"). It is evaluated and recorded but never vetoes, because promoting a
  preference to a filter would change the trading logic.

Compiled: **24 documents, 423 nodes, covering 392 specification elements.**

### 2.1 Coverage summary

| | count |
|---|---|
| strategies compiled | 24 |
| executable | 14 |
| blocked pending an explicit operationalisation | 10 |
| compiled nodes | 423 |
| specification elements accounted for | 392 / 392 |
| distinct parameters | 41 (13 `frozen_required`, 28 `frozen_choice`) |
| knowledge-base ids referenced | all resolve against the repository |

---

## 3. Required features

`requirements/feature_registry.json` — **35 features**, each a pure function of the visible bar
window plus frozen parameters, each mapping 1:1 onto a primitive in the approved library:

swing points (short/intermediate/long term) · structure state and governing point · displacement
and the displacement leg · fair value gap, consequent encroachment, mitigation state and inversion
· order block, breaker/mitigation test, zone overlap · liquidity pools and equal highs/lows ·
sweep/raid classification · reclaim test · strict MSS and internal-vs-external scope · dealing
range, equilibrium, premium/discount, depth fraction · Fibonacci levels, OTE membership,
retracement class · session membership and completed session ranges · period opens · three bias
methods · draw on liquidity · Power-of-3 phase · SMT divergence · position size and R multiple ·
the pre-entry checklist gate. Plus five non-concept helpers (bar access, latest index, tick
offset, midpoint, min/max pick).

Wherever the reference implementation `strategy_reearcher/engine/ict_primitives.py` already covers
an operation, the feature delegates to it rather than re-deriving it, so each rule has exactly one
definition in the codebase.

---

## 4. Required timeframe data

`requirements/timeframe_requirements.json` — per strategy: the timeframe **roles**, the candidate
timeframes the specification names for each, minimum history, whether a second correlated
instrument is needed, which period opens are required, and any external feed.

* Timeframes used across the catalog: `1m 3m 5m 15m 1h 4h 1d 1w`.
* The **execution timeframe** is the fastest non-optional role; it is the only clock on which
  fills occur.
* Every bar must carry a timezone-aware `close_time`: all session windows are anchored to New York
  time and shift with DST (BEG-M08-R05), which the zone conversion handles.
* One strategy (S22) additionally requires a time-aligned second instrument feed.

---

## 5. Required market-state calculations

`requirements/market_state_requirements.json` — **11 calculations**: swing registry, structure,
controlling range, pool registry, array registry, session calendar, period opens, bias state,
Power-of-3 state, correlated-instrument view, risk state.

All of them are **recomputed from the visible window at every decision bar** rather than carried
forward. That is what makes the look-ahead control and the determinism contract provable rather
than merely claimed — there is no mutable state that could leak backwards or forwards.

---

## 6. Executable implementation and the determinism contract

`engine/backtest.py`. Execution model:

* one clock (the execution timeframe), one position at a time, so trade order never depends on
  evaluation order;
* setup events **latch**: an event's bar index is fixed when it first evaluates true and is never
  revised;
* context / prerequisite / no-trade gates are checked when a setup starts and re-checked at the
  entry bar (ADV-M16-R08);
* intrabar ambiguity is resolved by one declared rule (`intrabar_policy`), never by data order;
* management begins on the bar after entry.

Three decisions no specification makes are **run-configuration fields with no defaults**, recorded
in every run manifest so results can never be attributed to the source: `setup_expiry_bars`
(how long a partially formed setup stays live), `intrabar_policy`, and latch supersession (a
pending setup is abandoned when the market prints a *different* first event). See DSL_SPEC §8.3.

**Determinism.** Each run emits a manifest with the SHA-256 of the compiled DSL, the frozen
configuration, the instrument configuration, the bar data and the resulting trade list. The test
suite asserts that two independent runs agree on all five digests, that reordering the
configuration dictionary changes nothing, and that changing a single frozen parameter changes both
the configuration digest and the trades.

**Nothing is guessed.** A parameter the knowledge base does not specify has no default anywhere:
`FrozenConfig.require` raises, and `dsl.prepare` fails before a single bar is processed. A
`frozen_choice` value outside the documented menu is rejected with the menu quoted back.

---

## 7. Conditions that are not computationally representable

`dsl/unsupported_registry.json` — **58 items**, none of them silently approximated.

| Reason code | Items | Meaning |
|---|---|---|
| `GAP_REQUIRES_FROZEN_OPERATIONALISATION` | 26 (15 blocking) | The source names the condition but supplies no computational test. A recorded operationalisation makes it computable; the engine will not invent one. |
| `UNSUPPORTED_PROCESS` | 15 | Human process/discipline instructions (write the narrative stack pre-session, journaling, overtrading). Not market conditions. |
| `UNSUPPORTED_SUBJECTIVE` | 14 | Gestalt judgments with no price test ("obvious at a glance", "clean array", "prolonged contraction", "cleaner array and better own-narrative alignment"). Each carries an `effect_if_unenforced` disclosure. |
| `UNSUPPORTED_EXTERNAL_DATA` | 3 | Needs a non-price feed the specification does not define (economic calendar). |

**Ten strategies are `blocked`**: S06, S08, S10, S13, S17, S19, S20, S22, S23, S24. A blocked
document still compiles, still validates and still publishes its requirements — it simply refuses
to execute until every blocking item has an explicit entry in the run configuration's
`operationalisations` map, which is then copied into the run manifest. The distinct blockers are:

| Item | What is missing |
|---|---|
| `U-RECLAIM` | No passage defines the price test that constitutes a "reclaim" (CF-14). Three candidate tests are offered as a frozen choice. |
| `U-IFVG-HOLD` | "Demonstrably holding" after an inversion is never given a price test. |
| `U-SMT-CORR` | "Strong, stable current correlation" has no threshold and no comparison window. |
| `U-S08-01…05` | The London Close model has no entry zone, no trigger, no stop and no extension measure. |
| `U-S10-01` | The scalping checklist makes "single-impulse objective" mandatory but gives it no measure. |
| `U-S23-01/02` | The weekly accumulation range is "often Monday" while rigid day-of-week rules are forbidden; and every execution element delegates to the gated daily model, so the document is a filter, not a standalone strategy. |
| `U-S24-01` | The session accumulation range has no definition. |

Alongside these, every no-trade condition each specification lists carries an explicit
**disposition** in the compiled document: `compiled`, `enforced_by_sequence`,
`enforced_by_feature`, `enforced_by_engine`, or an unsupported item. Nothing is dropped in
silence.

---

## 8. Validation tests

`python3 -m strategy_compiler.tests.run_all` — **41 tests, all passing**.

| Group | What it proves |
|---|---|
| `test_dsl_schema` | All 24 documents load and validate; every approved specification was compiled; expressions call only the closed feature and market-state sets; every node is traceable; no parameter carries a hidden default. |
| `test_translation_fidelity` | Every specification element is compiled, unsupported or unconstrained — none dropped, none invented; every node's source text is byte-identical to the specification; every knowledge-base id resolves; only catalogued primitives are used; every parameter traces to the parameter register; every no-trade condition is dispositioned; recompilation is byte-stable. |
| `test_features` | Feature values match knowledge-base worked examples (consequent encroachment INT-M04-EX01 and BEG-M11-EX01, Fibonacci/OTE BEG-M07-C03, alternative constants INT-M07-R02, risk and R multiple BEG-M12-EX01, sizing INT-M12-EX01); a wick-only breach is not an MSS (BEG-M03-R01); unfrozen parameters raise; off-menu choices are rejected; the reclaim and inversion tests refuse to run without a recorded operationalisation. |
| `test_lookahead` | No feature's value at bar *t* changes when bars after *t* are added (12 probes × every other bar); a session range is invisible until its window closes; swing points are published exactly one candle late. |
| `test_execution` | The compiled S01 document executes the eleven-step chain in order and enters at the consequent encroachment with the stop just beyond the sweep extreme; two runs agree on all five digests; configuration ordering is irrelevant; one parameter change moves both the configuration digest and the trades; missing parameters, off-menu choices and missing execution-model parameters all refuse to start; blocked strategies refuse to run without an operationalisation. |
| `test_smoke_all_strategies` | Every non-overlay compiled strategy loads, prepares and runs end to end. |

---

## 9. Reporting obligation

Results produced by this engine describe **the operationalisation**, not ICT doctrine
(ADV-M18-R01). Every frozen parameter, every recorded operationalisation of a blocking item, and
the three execution-model parameters must be reported alongside any performance number, and must
have been fixed before those numbers were computed (ADV-M18-R02, ADV-M18-R04). The run manifest
carries the digests that make that claim checkable after the fact.
