# ICT Strategy Research Catalog

**Source of truth:** the `sebuleni-llm` knowledge base (44 modules; 313 concepts, 187 rules, 21 strategies, 16 examples, 30 relationships, 47 no-trade conditions, 19 contradictions, 1 empirical claim).
**Constraint honoured:** every component below references knowledge-base objects. Nothing was added from outside the KB. Where the KB gives no value, the field says `unspecified` and the researcher must freeze a value *before* testing and report it as a research parameter (ADV-M18-C03), never as doctrine (ADV-M18-R01).

Machine-readable companions (all cross-validated against the repository — 900 distinct KB references, 0 missing):

| File | Contents |
|---|---|
| `primitives.json` | 26 detection primitives (P-*) — the mechanical labeling rules every strategy is composed from |
| `strategies.json` | 24 strategy specifications (10 base/component, 14 documented variants) |
| `comparison_tests.json` | 19 comparison / ablation experiments, each varying one KB-documented component |
| `concept_interactions.json` | 12 complementary confluences, 16 conflicts/unresolved variances, 4 non-removable dependency chains, 8 items deliberately *not* constructed |
| `parameter_register.json` | 58 parameters with status: specified / range / alternatives / heuristic-unfixed / unspecified |
| `validate.py` | Re-runs the reference check: `python3 validate.py <kb_repo_root> <this_dir>` |
| `ict_primitives.py` | Reference implementation of the primitives; every KB-unspecified threshold is a *required* `FrozenParams` field with no default (raises `UnspecifiedParameter`) |
| `test_primitives.py` | 30 unit tests whose expected values come only from KB worked examples — `python3 test_primitives.py` |
| `research_config_template.json` | Freeze-before-testing worksheet: every unspecified/alternative parameter with its KB status and source |
| `kb_numeric_audit.md` | Numeric consistency audit of the KB's worked examples (3 example-figure errors found; no rule affected) |

---

## 1. Method

1. **Inventory.** Read every module JSON: all 21 `StrategyObject`s, all rules, no-trade conditions, relationships, contradictions, examples, and the advanced `module_synthesis` items.
2. **Primitive extraction.** Reduced the KB's detection criteria to 26 reusable primitives (swing points, structure state, displacement, FVG/CE, OB, Breaker/Mitigation, liquidity pools, sweep/raid, MSS strict + internal/external, dealing range, Fibonacci/OTE, sessions, Asian range, three bias methods, DOL, PO3, SMT, stop options, target options, risk, pre-entry gate). Each carries its KB refs, look-ahead timestamp, and its unspecified parameters.
3. **Strategy composition.** Every KB `StrategyObject` became a base strategy. Documented combinations (the KB's own worked examples, selection scenarios, session/PO3 mappings, SMT integration, weekly gating) became variants with explicit `parent_strategy_id`.
4. **Comparison design.** Wherever the KB documents *two or more* ways to operationalise the same component (kill-zone bounds, Fib anchor, stop reference, MSS strictness, bias method, Breaker test, entry trigger…), or asserts a component is *necessary* (sweep, P/D filter, time filter, HTF bias), a comparison arm or ablation arm was defined. Ablation arms are research controls, not proposed strategies.
5. **Validation.** `validate.py` confirms every referenced ID exists in the repository.

The KB's own research module (ADV-M18) supplies the test protocol: define → label in-sample → measure → freeze → out-of-sample → freeze → forward; metrics = N, win rate, avg win/loss (R), expectancy, max drawdown, R-distribution, time in trade; multi-regime, multi-instrument samples; hindsight/look-ahead controls. The Capstone (ADV-M19-S01) sets the minimum sample: 100 trading days / 50 complete setups with a blind-chart subset.

---

## 2. The shared skeleton

All directional models in the KB share one dependency chain (BEG-M11-R01, INT-M03-R04, ADV-M06-R04, ADV-M11-C01):

```
HTF bias + named DOL  →  correct P/D half of controlling range  →  liquidity event (sweep of origin pool)
  →  displacement  →  MSS  →  PD array left by the displacement  →  retracement into array
  →  entry (CE / OB / OTE)  →  stop beyond the structural premise  →  targets: IRL partial → DOL
```

Removing a link converts the model into "a different, unvalidated approach that happens to share some of its vocabulary" (BEG-M13-NT01). Long models require **discount + SSL origin + bullish bias**; short models require **premium + BSL origin + bearish bias**; identical standards on both sides (ADV-M12-R02).

---

## 3. Strategy catalog

Legend — *Spec*: F = fully specified in the KB, P = partially specified (missing element listed). *Dir*: L long, S short, R reversal-bidirectional (direction set by which pool is swept, subject to bias filter).

### 3.1 Base models (direct implementations of KB StrategyObjects)

| ID | Name | KB source | Dir | Session | Spec | Key unspecified elements |
|---|---|---|---|---|---|---|
| S01 | ICT Buy Model — Eleven Steps | BEG-M11-S01 | L | any (example: LOKZ) | F | displacement thresholds, sweep penetration, stop buffer |
| S02 | ICT Sell Model — Eleven Steps | BEG-M12-S01 | S | any (example: 14:00 ET) | F | as S01 |
| S03 | Bullish Discount Framework | INT-M06-S01 | L | unspecified | F | "decisive close"; stop ref (displacement origin vs range low) |
| S04 | Bearish Premium Framework | INT-M06-S02 | S | unspecified | F | as S03 |
| S05 | Power of 3 Daily Template | BEG-M09-S01 (+INT-M10, ADV-M08) | R | Asia→London→NY mapping | P | stop (deferred), manipulation reversal window, daily-open definition |
| S06 | Judas Swing — London Open | BEG-M08-S01 | R | LOKZ 02:00–05:00 ET | P | HTF bias precondition, stop/target (deferred to M7), "reclaim" definition |
| S09 | OTE Entry Zone (component) | BEG-M07-S01 | L/S | unspecified | P | LTF confirmation signal; Fib anchor conflict |

### 3.2 Session variants of the sweep sequence

| ID | Name | KB source | Dir | Session | Spec | Notes |
|---|---|---|---|---|---|---|
| S07 | NY Open KZ sweep sequence | BEG-M08-S02 | R | NYKZ (3 documented windows) | P | invalidation/stop/target only "as in London" |
| S08 | London Close raid → retrace to open | BEG-M08-S03 | R | 10–12 ET *or* 08–09 ET (non-overlapping) | P | KB grades it lowest-probability; use as stratification bucket |
| S10 | Daily Scalping | BEG-M13-S01 | L/S | selected KZ | P | "nearby pool" / single impulse undefined; fragile to costs |

### 3.3 Advanced variations (skeleton ADV-M11-S00 / ADV-M12-S00)

| ID | Variation | KB source | Dir | Spec | Trade-level invalidation |
|---|---|---|---|---|---|
| S11 | A — FVG / OTE continuation | ADV-M11-S01 | L | F | close below displacement origin or array far side |
| S12 | B — Breaker continuation | ADV-M11-S02 | L | F | close below Breaker extreme or its displacement origin |
| S13 | C — IFVG continuation | ADV-M11-S03 | L | P | *unspecified in source* — freeze from ADV-M16-R04 options |
| S14 | D — HTF array + LTF confirmation | ADV-M11-S04 (+INT-M08-R04) | L | P | LTF-tight vs HTF-wide both documented |
| S15–S18 | A–D bearish mirrors | ADV-M12-S01..S04 | S | F/F/P/P | mirror of S11–S14 (ADV-M12-REL01) |

The KB is explicit that "Variation A/B/C/D" are the book's own pedagogical labels, not official ICT model names (ADV-M11-AMB01). Selection among them is narrative-driven (ADV-M11-R02, ADV-M15-C04): clean FVG/OB in the right half → A; violated opposing OB being revisited → B; inverted FVG demonstrably holding → C; reaction at a weekly/daily array with LTF only refining → D.

### 3.4 Documented combinations (variants)

| ID | Name | Composition (all KB-documented) | Dir | Spec |
|---|---|---|---|---|
| S19 | Buy Model @ London Open, Asian-low sweep | S01 × BEG-M08-S01 × BEG-M09-S01 × conditional bias ADV-M10-R03; worked in BEG-M11-EX01, INT-M09-EX01, INT-M10-EX01, INT-M11-EX01, INT-M12-EX01 | L | F |
| S20 | Sell Model @ London Open, Asian-high sweep | mirror; BEG-M08-C06 / BEG-M08-EX01 | S | F |
| S21 | New York continuation into the London array | ADV-M14-R03, INT-M09-R05/R06, INT-M09-EX01, ADV-M01-C09 — no new NY sweep required; entry trigger has two documented forms (limit at CE vs LTF confirmation) | L/S | F |
| S22 | Variation A + SMT confirmation layer | ADV-M13-R01..R07, ADV-M15-C04 "SMT-Confirmed Day" — SMT never the primary model | L/S | P |
| S23 | Weekly-PO3 / weekly-range gate over daily models | INT-M10-R02, ADV-M08-R02/R03, ADV-M14-C06 | L/S | P |
| S24 | Session-PO3 timed entry inside a clear daily PO3 | INT-M10-R03, ADV-M08-C04 | L/S | P |

---

## 4. Comparison & ablation tests (one component varied per test)

| Test | Component | Arms (all from the KB) | KB claim under test |
|---|---|---|---|
| CT-01 | Entry level | CE · FVG edge · OTE 70.5% · OB boundary · OB∩OTE | ADV-M16-R03 hierarchy; INT-M04-R02 "reacts at CE" |
| CT-02 | Stop reference | sweep extreme · displacement origin · array far side · LTF swing · OB-vs-79% · HTF-wide (Var. D) | INT-M12-R02 / ADV-M17-R01 logical stops |
| CT-03 | Target policy | nearest pool · IRL→ERL · −27/−62% · partial+runner · fixed R minimum | INT-M12-R03 vs ADV-M17-R04 (R:R as filter vs outcome) |
| CT-04 | Kill-zone bounds + **time-filter ablation** | LOKZ 2–5 / 2–4; NYKZ 7–10 / 8–11 / 8:30–11 / 7–9; Asian 20–22 / 20–00; no filter | Time & Price Theory (BEG-M08-C01, ADV-M07-R04) |
| CT-05 | **P/D filter ablation** | correct half · deep zone (outer 20–25%) · both TF halves · none | INT-M06-EX01 counter-example; INT-M04-R04 |
| CT-06 | OTE confluence | OTE alone · FVG alone · FVG∩OTE · OB∩OTE · triple · OTE without raid | BEG-M07-EMP01 (~55–60% standalone, hedged) |
| CT-07 | MSS strictness/scope | strict · body-only (CHoCH) · wick (negative control) · +not-reclaimed · ST vs IT swing · internal vs external | BEG-M03-R02, INT-M03-R03/R05 |
| CT-08 | Fib anchor & levels | body-to-body · sweep-wick origin · 0.62/0.705/0.79 · 0.618/0.786 | BEG-M07-R01 **vs** INT-M07-R01 conflict |
| CT-09 | Bias method + **HTF ablation** | M/W opens · structural · 3-factor daily · single-MSS trick · full bias statement · none | BEG-M02-R01, ADV-M10-R06, INT-M08-NT01 |
| CT-10 | **Sweep ablation** | any pool · equal H/L · session vs prior-day vs HTF pool · none | "no sweep, no trade" (BEG-M11-S01), INT-M03-R04 |
| CT-11 | Reclaim window | 2 · 3 · frozen "reasonable" · close-vs-wick reclaim | BEG-M08-R06 vs BEG-M09-R02 |
| CT-12 | Displacement thresholds | body/range · range multiple · FVG required · break required | BEG-M05-AMB01; ADV-M18-R06 perturbation robustness |
| CT-13 | Variation A/B/C/D stratification | 8 advanced variants, long vs short symmetry | ADV-M18-C08, ADV-M05-R02 hierarchy |
| CT-14 | SMT on/off | aligned · absent · contradicting · weaker-instrument selection | ADV-M13-R04/R06 |
| CT-15 | Weekly gate on/off | distribution-only · reduced size in accumulation · none | ADV-M08-R04, INT-M10-R04 |
| CT-16 | Breaker test | body-close · sweep+MSS · all quality filters | INT-M05-R02 vs BEG-M06-R03 |
| CT-17 | Session stratification | LOKZ · NYKZ fresh · NYKZ continuation · London Close · Asia (neg.) · midday (neg.) | BEG-M08-R03, ADV-M14-R03 |
| CT-18 | TF synchronization | synchronized · false conflict · true conflict (counter-narrative bucket) | ADV-M09-R02 |
| CT-19 | Entry trigger | resting limit · 1-min confirmation · full LTF conditioning | ADV-M16-R02 (beginner permits limit; advanced forbids un-confirmed touch) |

---

## 5. Conflicts the researcher must freeze (from `concept_interactions.json`)

The KB is transparent about its own variances. These are **not** filled in; they are parameters with documented alternatives:

1. Fibonacci anchor: body-to-body (BEG-M07-R01) vs sweep-wick origin (INT-M07-R01).
2. OTE constants 0.62/0.705/0.79 vs 0.618/0.786 (INT-M07-R02).
3. Kill-zone clock bounds — including the non-overlapping London Close windows (BEG-M08-AMB01/AMB02).
4. Manipulation reversal window: ~2–3 candles (Judas) vs "reasonable number" (PO3).
5. Trade-stop reference: five documented logical placements.
6. R:R as minimum threshold (INT-M12-R03) vs R:R as outcome only (ADV-M17-R04).
7. Risk fraction: ~1–2% (BEG) / 0.5–1% (INT) / 0.25–1% (ADV).
8. Breaker qualification: body-close test vs sweep+MSS.
9. Daily-bias method: three-factor vs single-MSS trick.
10. Displacement thresholds (60–70% body heuristic, explicitly unfixed) and equal-highs tolerance (5–10 pips, secondary).
11. Daily-open anchor vs New York midnight (thin support).
12. "Reclaim" semantics in the Judas rule are undefined.
13. Entry trigger: limit at zone (beginner) vs LTF confirmation required (advanced).
14. Judas Swing's HTF-bias precondition: absent at beginner level, required at intermediate/advanced.

---

## 6. Deliberately not constructed

| Item | Why |
|---|---|
| Silver Bullet (10:00–11:00 ET) | Named once, no rules, not a KB concept (BEG-M08-C09) |
| Rejection Block | Evidence class D; KB warns against elevating it (ADV-M05-C05) |
| Liquidity Void / Balanced Price Range entries | No entry/invalidation rules; fluid boundary with FVG (ADV-M03-AMB01) |
| Counter-narrative scalp | Permitted only with reduced probability and tight risk; no mechanics (INT-M08-R03) — kept as CT-18 arm C |
| "2022 Model", "Market Maker Buy Model" | Only mentioned as variations of the same eleven steps (BEG-M11-REL01) |
| Any indicator filter | Research malpractice while calling the system ICT (ADV-M18-AMB01) |
| Capstone (ADV-M19-S01) | A research protocol, adopted here as the testing standard, not a trade model |

---

## 7. How to operationalise a strategy for backtesting

For each strategy the KB's own minimum-elements list (ADV-M18-R02) maps to the spec fields:

| ADV-M18-R02 element | Where it lives |
|---|---|
| Instrument & timeframes | `timeframe` + instrument chosen by researcher (KB examples: EUR/USD, XAU/USD, ES/NQ) |
| HTF bias rule (no look-ahead) | `context.htf_bias_required` → P-BIAS-01/02/03 |
| Liquidity origin rule | `prerequisites` → P-LIQ-01, raid condition P-LIQ-02 (freeze Y penetration, Z reclaim bars) |
| Displacement rule | P-DISP-01 (freeze range multiple, lookback, body ratio) |
| MSS rule | P-MSS-01 (which swing tier, body close) |
| Entry array rule | P-FVG-01 / P-OB-01 / P-OB-02 / P-FVG-02 / P-FIB-01 |
| Entry trigger | `entry.trigger_options` (choose one arm; CT-19) |
| Invalidation rule | `stop_invalidation` (choose one P-STOP-01 option; CT-02) |
| Target rules | `target` (choose one P-TARGET-01 option; CT-03) |
| Session/time filter | `session` (choose one P-TIME-01 window; CT-04) |
| Sizing & risk | P-RISK-01 (freeze fraction within KB range) |

Freeze every choice in writing, then follow ADV-M18-R05. Report per ADV-M18-R07 and end with the mandatory statement that results describe the operationalisation, not ICT doctrine.
