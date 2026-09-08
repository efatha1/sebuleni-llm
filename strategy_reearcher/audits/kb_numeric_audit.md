# Knowledge-Base Numeric Consistency Audit

Produced while replaying the KB's worked examples through `ict_primitives.py` (30/30 fixtures pass).
Each finding cites the KB object. These are **source-text observations**, not corrections — the KB is the
sole authority and its `raw_sections` remain verbatim; the findings tell a researcher which example
figures can be used as test vectors and which cannot.

| # | KB object | Finding | Severity | Effect on strategy specs |
|---|---|---|---|---|
| A1 | INT-M07-EX01 | Fibonacci 1.0810 → 1.0910 gives 62% = **1.0848**, 70.5% = **1.08395**, 79% = **1.0831**. The example states the OTE zone as "1.0848 – 1.0867" and 70.5% "near 1.0857". 1.0867 is the 43% level, not 79%. The stated band runs the wrong way (shallower than 62%). | Numeric error in source example | None — the *rule* (INT-M07-R02) is consistent and is what S09/S01 implement; the example's figures must not be used as a test vector. The FVG (1.0835–1.0850) *does* overlap the correctly computed OTE (1.0831–1.0848), so the narrative conclusion survives. |
| A2 | INT-M07-EX02 | Fibonacci 1.2635 → 1.2540 gives OTE **1.2599 – 1.2615**; example states "roughly 1.2590 – 1.2605" (≈ 9–10 pips low). Both bands are inside premium (EQ 1.2575), so the P/D conclusion holds. | Approximation error | None on rules; do not use as exact fixture. |
| A3 | BEG-M11-EX01 | "Risk approximately 88 pips" for 1.08118 → 1.08030 (= 0.00088) and "over 1,300 pips" for 1.08118 → 1.09420 (= 0.01302). Both are 10× the standard 4-decimal pip; the example is counting 5th-decimal points/pipettes. Internally consistent (same unit both times). | Unit-labelling ambiguity | Freeze the pip definition per instrument in the research config; the R-multiple (T2 ≈ 14.8 R) is unaffected. |
| A4 | BEG-M11-EX01 | Entry 1.08118 "at the FVG midpoint" — true midpoint of 1.08095–1.08142 is 1.081185 (rounded down). 70.5% at 1.08118 from low 1.08042 implies a post-MSS high ≈ 1.08300 (not stated) — consistent with "price continues briefly higher after the MSS" beyond the 1.08185 displacement high. | Rounding only | Test tolerance set to half a pipette. |
| A5 | BEG-M12-EX01 | 70.5% "at approximately 2,650.10" from high 2,655.80 implies a leg low ≈ **2,647.7**, but the text says the leg runs to the "post-MSS low" and price "continues briefly lower after the MSS" below the displacement low 2,644.20. Using 2,644.20 as the leg low, OTE = 2,651.4 – 2,653.4, which sits *above* most of the FVG (2,648.30–2,651.60). Either the leg low is unstated (~2,647.7) or the FVG/OTE "close alignment" claim is only marginal. | Internal inconsistency | The rule (Fib on swept extreme → pre-retracement extreme) is unambiguous; the example cannot serve as an exact fixture for the OTE step. Risk 6.50 / T1 5.70 / T2 31.9 figures check out. |
| A6 | BEG-M03-C01, C03 | Sequence 100→108→104→115→109→122 is called bullish with "at least two consecutive higher lows", but only two swing lows (104, 109) are listed — the second HL comparison requires counting the starting value 100 as the first low. | Implicit assumption | `structure_state()` treats sequence endpoints as turning points, as the example requires. Documented in the test file. |
| A7 | BEG-M08-R06 | "Confirm price does not reclaim the swept level within ~2–3 candles; if it does, treat as a genuine breakout." The direction/price test that constitutes a *reclaim* is never defined. | Definitional gap | Already registered as CF-14; `detect_sweep()` exposes penetration Y and window Z as required frozen parameters and labels raid vs continuation by a close back through the level, which the researcher must confirm matches their frozen reading. |
| A8 | BEG-M08-R03 / BEG-M08-AMB02 | London Close windows 10:00–12:00 vs 08:00–09:00 ET do not overlap. | Unresolved in source | S08 requires the window to be frozen; CT-04 compares. |
| A9 | INT-M12-EX01 | Entry 1.0865 / stop 1.0810 (55 pips) / partial 1.0920 / runner 1.1000 → partial = exactly **1.0 R**, runner = **2.45 R**. Consistent. | ✓ | Used as fixture for `position_size()`. |
| A10 | INT-M02-EX01, INT-M04-EX01, INT-M06-EX01, INT-M08-EX01, ADV-M02-C08, ADV-M03-C09, ADV-M05-C10 | All equilibrium, premium/discount, CE and nesting figures recompute exactly. | ✓ | Used as fixtures. |

## Implications for the catalog

* No strategy specification changes: every affected passage is an *example*, and the governing *rules* (INT-M07-R02, BEG-M07-R03, BEG-M05-R02, INT-M06-R02) are internally consistent and are what the specs implement.
* `test_primitives.py` uses only the figures that recompute (A4, A9, A10 and the Beginner 100→200 examples); A1, A2, A5 are excluded as fixtures.
* If the knowledge-base maintainers wish to record these, the appropriate schema object is `contradictions_or_ambiguities[]` (`resolution_status: unresolved_in_source`) on INT-M07 and BEG-M12, and a `confidence_note` on BEG-M11-EX01 about the pip unit — I have not modified the repository.
