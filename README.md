# ICT Knowledge Base — README

## What This Is
A structured, traceable knowledge base extracted from the single supplied source book:
**"UNDERSTANDING ICT — A Beginner's Structured Guide to the Inner Circle Trader Methodology"**
(a compiled text covering Beginner, Intermediate, and Advanced levels of the ICT trading methodology, 44 modules total).

This is the **sole authoritative source** for everything in this knowledge base. No outside trading
knowledge, conventional TA definitions, or invented thresholds have been added. Where the source book
itself could not verify a claim against primary ICT material, that hedge is preserved in the
`attribution_type` / `confidence_note` fields of each object.

## Directory Structure
```
knowledge_base/
  _schema/SCHEMA.md          <- Full schema definition (object types, fields, ID convention)
  index.json                 <- Master index: every module file, level, title, and object counts
  beginner/mod01..mod13.json  <- 13 modules (Price Fundamentals -> Daily Trading & Scalping)
  intermediate/mod01..mod12.json <- 12 modules (Advanced Market Structure -> Risk/Journaling)
  advanced/mod01..mod19.json  <- 19 modules (Institutional Price Delivery -> Complete ICT Narrative)
```

## How to Use This Knowledge Base
1. Start with `index.json` to see all 44 modules, their titles, and how many of each object type
   (concepts, rules, strategies, examples, relationships, no-trade conditions, contradictions) each contains.
2. Read `_schema/SCHEMA.md` to understand the object model before parsing module files programmatically.
3. Each module JSON file is self-contained and includes:
   - `module_intro` / `prerequisites_stated_in_text` / `module_objectives`
   - `concepts[]` — every named term/concept, mapped closely to the book's own definitional structure
   - `rules[]` — atomic, actionable rules (detection criteria, sequencing, confluence, invalidation, risk, time/session constraints, selection procedures)
   - `strategies[]` — only genuine tradable strategies/variants with identifiable context+setup+entry+invalidation+target (partially-specified ones are labeled as such with `missing_elements`)
   - `examples[]` — worked numeric/narrative examples from the text
   - `relationships[]` — cross-module and cross-concept relationships ("How These Concepts Connect" sections)
   - `no_trade_conditions[]` — explicit conditions under which the book says to stand aside
   - `contradictions_or_ambiguities[]` — places where the book itself flags disagreement, hedges, or unresolved variance (e.g., MSS vs BOS vs CHoCH terminology, Kill Zone time boundaries, Mitigation vs Breaker definitions)
   - `module_review_notes` — key terms, self-test questions, common misconceptions, and research sources as stated in the book
   - Advanced-level modules additionally have `module_synthesis` (worked narratives, failure conditions, common misinterpretations, evidence classifications that the book itself separates from atomic concepts)

## Key Structural Notes
- **Beginner Modules 1-10**: each concept follows the book's own 11-part structure (Definition, ICT's Meaning,
  Beginner Explanation, How to Identify, Example, What It Tells the Trader, Pairings, Framework Placement,
  Mistakes, Qualification, Source).
- **Beginner Modules 11-13**: strategy-first modules (ICT Buy Model, ICT Sell Model, Daily Trading & Scalping) —
  captured as `StrategyObject`s with full step sequencing and worked numeric examples.
- **Intermediate Modules 1-12** and **Advanced Modules 1-19**: use a numbered-topic structure
  (e.g. "3. The Dealing Range" with sub-sections). Each numbered topic became one `ConceptObject`,
  with a `raw_sections` field preserving the verbatim sub-section text for full traceability even where
  a normalized field (e.g. `detection_criteria`) could not be auto-mapped.
- **ID convention**: `{LEVEL}-M{module:2digits}-{TYPE}{seq:2digits}` where LEVEL ∈ {BEG, INT, ADV} and
  TYPE ∈ {C=concept, R=rule, S=strategy, EX=example, REL=relationship, NT=no-trade, AMB=contradiction}.
- **Strategy lineage**: Advanced Buy/Sell Model variations (A-D) reference their Beginner/Advanced parent
  strategies via `parent_strategy_id` (e.g. `ADV-M11-S01.parent_strategy_id = "ADV-M11-S00"`), letting an
  agent trace the full lineage from the Beginner 11-step model through to Advanced narrative-conditioned variants.

## Source-Authority Discipline Applied Throughout
- `"unspecified"` is used literally wherever the book does not give a value/threshold/detail — never filled in.
- `attribution_type` on every object is one of: `ICT_primary`, `community_interpretation`,
  `research_compiled_secondary`, or `book_synthesis` (the book's own advanced-level operational synthesis,
  explicitly labeled as such in the source, e.g. Evidence Classification "C" in Advanced modules).
- Genuine terminology debates documented by the book (e.g. MSS vs BOS vs CHoCH, Mitigation Block vs Breaker
  Block, Rejection Block as community vs core ICT, Kill Zone time-boundary variance) are captured as
  `contradictions_or_ambiguities` objects rather than silently resolved.
- Empirical/statistical claims (e.g. OTE standalone success-rate figures, Advanced Module 18's research
  methodology) are preserved with their original hedging language intact.

## Known Limitations (for the next agent to be aware of)
- A small number of auto-mapped `ConceptObject` fields (e.g. `definition`, `detection_criteria`) in
  Intermediate/Advanced modules may read as a best-effort fallback rather than a precisely labeled book
  subsection; in every such case, the full verbatim content is still available in that concept's
  `raw_sections` field, so no source content has been lost.
- Cross-references to specific page/paragraph numbers are not available (source was a .docx without stable
  pagination); `book_location` instead gives level + module number + module title + section heading, which
  is sufficient to relocate the passage in the module's original text.
