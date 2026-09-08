# Knowledge Base Schema — ICT Full Journey Guide

## Source Authority
The ONLY authoritative source is the supplied book: "UNDERSTANDING ICT — A Beginner's Structured Guide to the Inner Circle Trader Methodology" (which contains three bound levels: Beginner, Intermediate, Advanced). No outside trading knowledge, no invented thresholds, no conventional-TA definitions may be added. If the book does not specify a value/threshold/rule, the field must contain the literal string "unspecified" (or an object noting what is unspecified) — never a guess.

## Directory Layout
This is the repository root itself (no extra wrapper folder):
```
beginner/mod01_price_fundamentals.json ... mod13_daily_trading_scalping.json
intermediate/mod01_...json ... mod12_...json
advanced/mod01_...json ... mod19_...json
_schema/SCHEMA.md
index.json
```

## Per-Module JSON File Shape
Each module JSON file is one object:
```json
{
  "level": "beginner|intermediate|advanced",
  "module_number": 1,
  "module_title": "Price Fundamentals",
  "prerequisites_stated_in_text": "verbatim or paraphrased prerequisite note if the book states one, else 'unspecified'",
  "module_objectives": ["..."],
  "concepts": [ ConceptObject, ... ],
  "rules": [ RuleObject, ... ],
  "strategies": [ StrategyObject, ... ],
  "examples": [ ExampleObject, ... ],
  "relationships": [ RelationshipObject, ... ],
  "no_trade_conditions": [ NoTradeObject, ... ],
  "contradictions_or_ambiguities": [ ContradictionObject, ... ],
  "empirical_claims": [ EmpiricalClaimObject, ... ],
  "module_review_notes": {
    "key_terms": ["..."],
    "common_misconceptions": ["..."],
    "self_test_questions": ["..."] ,
    "research_sources_cited_in_text": ["..."]
  }
}
```
Omit an array's contents (use `[]`) only if that category truly has zero instances in the module — do not force content into a category to fill it.

## ConceptObject
Used for every named term/concept the module defines (e.g. Swing High, Displacement, Order Block, OTE, Kill Zone, Dealing Range, Draw on Liquidity, SMT, etc.). Map directly onto the book's own structure for that concept where the book uses its 11-part (or advanced-module numbered) format.
```json
{
  "id": "BEG-M01-C01",
  "kind": "concept",
  "name": "Swing High",
  "definition": "plain definition as stated in book",
  "ict_specific_meaning": "ICT-specific meaning/refinement as stated, or 'unspecified'",
  "detection_criteria": ["mechanical/identification rules, step by step, exactly as given"],
  "preconditions": ["what must be true/present before this concept/pattern is valid, if stated"],
  "numeric_or_narrative_example": "worked example given directly under this concept, if any, else 'none in source at this point' (full example may instead live in examples[] if book separates it)",
  "what_it_tells_the_trader": "as stated",
  "common_pairings": ["other concepts it is commonly combined with, as stated"],
  "framework_placement": {"comes_before": "...", "comes_after": "..."},
  "beginner_mistakes_or_misinterpretations": ["..."],
  "qualification_or_limits": "the book's stated qualification/limit text, verbatim or close paraphrase",
  "dependencies": ["concept ids or names this concept requires to be understood/valid first"],
  "timeframe_relationship": "any stated HTF/LTF relationship for this concept, else 'unspecified'",
  "attribution_type": "ICT_primary | community_interpretation | research_compiled_secondary | book_synthesis",
  "cited_sources_in_text": ["verbatim source citations listed under this concept's Source section, if present"],
  "book_location": {"level": "beginner", "module_number": 1, "module_title": "Price Fundamentals", "section_heading": "Swing High"},
  "confidence_note": "any hedge the book itself expresses (e.g. 'not directly verified from primary transcript')"
}
```

## RuleObject
Discrete, atomic rules that are NOT full concepts and NOT full strategies: sequencing rules, confluence rules, dependency rules, timeframe rules, session/time constraints, risk rules, invalidation rules, management rules, selection procedures/checklists, etc.
```json
{
  "id": "BEG-M04-R01",
  "kind": "rule",
  "rule_type": "sequencing | confluence | dependency | timeframe_relationship | time_session_constraint | trade_management | risk | selection_procedure | invalidation | detection_criteria | precondition | other",
  "statement": "the rule stated as precisely as the book states it",
  "applies_to": ["concept or strategy names/ids this rule governs"],
  "conditions": ["itemized conditions, if the rule is conditional/step-based"],
  "exceptions_or_qualifiers": "as stated, else 'unspecified'",
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."},
  "attribution_type": "ICT_primary | community_interpretation | research_compiled_secondary | book_synthesis"
}
```

## StrategyObject
Use ONLY for explicit or hidden tradable strategies/models that have (or partially have) context+setup+entry+invalidation+target. This includes the ICT Buy Model, ICT Sell Model, Daily Trading/Scalping routine, Silver Bullet (if named), and each numbered "Variation A/B/C/D" in intermediate/advanced Buy/Sell Model modules.
```json
{
  "id": "BEG-M11-S01",
  "kind": "complete_strategy | strategy_variant | strategy_component",
  "name": "ICT Buy Model — The Eleven Steps",
  "parent_strategy_id": "id of parent strategy if this is a variant/component, else null",
  "context": {"htf_bias_required": "...", "session_or_time": "...", "other_context": "..."},
  "setup": ["ordered setup conditions/steps exactly as listed"],
  "entry_condition": "as stated, else 'unspecified'",
  "invalidation_or_stop": "as stated, else 'unspecified'",
  "target_or_exit": "as stated, else 'unspecified'",
  "trade_management_rules": ["as stated"],
  "sequencing_steps_verbatim_order": ["step 1 ...", "step 2 ...", "..."],
  "eligibility_checklist": ["if the book gives one, list items"],
  "specificity_status": "fully_specified | partially_specified | unspecified",
  "missing_elements": ["which of context/setup/entry/invalidation/target are missing or vague, if partially specified"],
  "worked_example_ref": "id of linked ExampleObject if one exists",
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."},
  "attribution_type": "ICT_primary | community_interpretation | research_compiled_secondary | book_synthesis"
}
```

## ExampleObject
```json
{
  "id": "BEG-M01-EX01",
  "kind": "example",
  "example_type": "numeric_price_sequence | worked_narrative | visual_reference_description",
  "linked_concept_or_strategy_ids": ["..."],
  "content": "the example content, preserved closely (numbers/sequences exact)",
  "interpretation_given_in_text": "what the book says this example demonstrates",
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."}
}
```

## RelationshipObject
Cross-module / cross-concept relationships, confluence stacks, "How These Concepts Connect" sections, timeframe-role relationships (HTF narrative/LTF entry), etc.
```json
{
  "id": "BEG-M01-REL01",
  "kind": "cross_module_relationship | confluence_relationship | timeframe_relationship | sequencing_relationship",
  "statement": "as stated in the book",
  "involved_concepts": ["..."],
  "involved_modules": ["Module X (level)", "..."],
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."}
}
```

## NoTradeObject
```json
{
  "id": "BEG-M11-NT01",
  "kind": "no_trade_rule",
  "statement": "condition under which the book says NOT to trade / stand aside",
  "applies_to_strategy_ids": ["..."],
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."}
}
```

## ContradictionObject
Use when the text is internally ambiguous, hedges itself, flags a community-vs-ICT distinction, or seems to conflict with another passage.
```json
{
  "id": "BEG-M01-AMB01",
  "kind": "contradiction_or_ambiguity",
  "description": "what is ambiguous/contradictory and why",
  "passage_a": {"text": "...", "book_location": {...}},
  "passage_b": {"text": "...", "book_location": {...}},
  "resolution_status": "unresolved_in_source | resolved_in_source | book_flags_as_community_vs_ICT"
}
```

## EmpiricalClaimObject
Use for any claim in the text about how often something works, statistical/backtested performance, or research/testing findings (common in Beginner Module 7's OTE success-rate discussion and Advanced Module 18 "Research & Model Validation"). Do NOT fold these into `ContradictionObject` — a hedged statistic is not the same thing as two conflicting book passages.
```json
{
  "id": "BEG-M07-EMP01",
  "kind": "empirical_claim",
  "claim": "the statistical/performance claim as stated in the book",
  "figures_given": "the specific numbers/percentages/rates stated in the book, or 'unspecified' if the book withholds a figure",
  "hedge_language": "the book's own hedging/confidence language surrounding this claim, verbatim or close paraphrase (e.g. 'general, source-reported approximations rather than precisely verified statistics')",
  "linked_concept_or_strategy_ids": ["..."],
  "book_location": {"level": "...", "module_number": 0, "module_title": "...", "section_heading": "..."},
  "attribution_type": "ICT_primary | community_interpretation | research_compiled_secondary | book_synthesis"
}
```

## Classification Discipline (mandatory)
- A concept is NOT a strategy just because it sounds tradable. Only classify as `complete_strategy` / `strategy_variant` / `strategy_component` if the passage supplies (even partially) context+setup+entry+invalidation+target.
- If a strategy-like passage is missing one or more of context/setup/entry/invalidation/target, set `specificity_status: "partially_specified"` and list `missing_elements`. Never invent the missing piece.
- `empirical_claim` = any claim in the text about how often something works, statistical performance, or research/testing findings (common in advanced Module 18 "Research & Model Validation") — tag these distinctly as a first-class `EmpiricalClaimObject` (kind: "empirical_claim", see object template above) and never state them as more certain than the book does. Do not represent an empirical claim as a `ContradictionObject` merely because the book does not give every figure — an absence of a numeric figure is not a second conflicting passage.
- Preserve the book's own hedging language ("Community interpretation:", "not directly verified", "corroborated across secondary sources") in `attribution_type` and `confidence_note`/`cited_sources_in_text` — do not launder a hedged claim into an unhedged one.
- Where the book itself says something is unspecified, undefined, left to the trader, or "the book does not specify," reproduce that as `"unspecified"` plus a short note — do not fill the gap with outside knowledge.
- Every object must carry `book_location` sufficient to find the passage again (level, module number, module title, section heading) without rereading the whole book.

## ID Convention
`{LEVEL}-M{module_number:2digits}-{TYPE}{sequence:2digits}`
LEVEL prefixes: BEG (beginner), INT (intermediate), ADV (advanced).
TYPE prefixes: C=concept, R=rule, S=strategy, EX=example, REL=relationship, NT=no-trade, AMB=contradiction/ambiguity, EMP=empirical claim.
Example: `INT-M05-S02` = Intermediate Module 5, second strategy object.
