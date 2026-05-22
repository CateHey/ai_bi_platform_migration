# VizShifter — Presentation Slides Plan

## Marking Criteria Mapping

The presentation is graded on 4 criteria with unequal weights. The slide deck is designed to maximize all four, especially Innovation (35%) and Completeness (30%) which together represent 65% of the grade.

| Criterion | Weight | Target Band | Strategy |
|-----------|--------|-------------|----------|
| Slides | 15% | Excellent | Clear structure (agenda), defined scope (RQ slide), diagrams over text, keep purple theme |
| Presentation | 20% | Excellent | Demo pause point, concrete examples for Q&A, speaker prep notes |
| Excellence, Innovation | 35% | Excellent | **3 dedicated data science slides** (RAG, Semantic DAX, Complexity Scoring) |
| Completeness | 30% | Excellent | **Actual results** (metrics table, translation examples, demo), not just a plan |

---

## Changes from Previous Semester Slides

The previous semester deck had 12 slides. This plan produces 16 slides.

| Previous Slide | Action | New Slide |
|----------------|--------|-----------|
| 1. Title "Migration Tool Qlik to Fabric" | Refine title | 1. Title |
| — | **NEW** | **2. Agenda** |
| 2. Key Definitions | **REMOVE** (audience = postgrad examiners, already know BI) | — |
| 3. Why is migration important | Refine | 3. The Problem |
| 4. Gaps in Current Migration Approaches | Keep as-is (strong) | 4. Current Tool Gaps |
| 5. Important Concepts | **REMOVE** (redundant for postgrad) | — |
| — | **NEW** | **5. Research Question & Scope** |
| 6. Proposed Solutions | Refine, update screenshot | 6. Solution Overview |
| 7. Technical Architecture | Update to 8 steps | 7. Pipeline Architecture |
| — | **NEW** | **8. RAG for Script Translation** |
| — | **NEW** | **9. Semantic DAX Translation** |
| — | **NEW** | **10. Complexity Scoring** |
| — | **NEW** | **11. Live Demo** |
| — | **NEW** | **12. Quantitative Results** |
| — | **NEW** | **13. Translation Examples** |
| 8 + 9. Exploratory Analysis I & II | Merge into one | 14. Exploratory Analysis |
| 10. Validation Plan | **REMOVE** (replaced by actual results in slides 12-13) | — |
| 11. Conclusions and Future Work | Refine, add contributions | 15. Conclusions & Future Work |
| 12. Thank You | Keep | 16. Thank You / Q&A |

**Summary: Removed 3 weak slides, added 7 high-value slides.**

### Why these removals?

- **Key Definitions:** The audience is postgraduate examiners who already understand BI, Power BI, and QlikView. Spending a full slide defining "Cloud: Computing resources that can easily scale" wastes time that should go to data science content (35% of grade).
- **Important Concepts:** Semantic models, expressions, and layout are explained implicitly throughout slides 7-10 where they appear in context of the actual work.
- **Validation Plan:** The previous "Validation Plan" slide only listed future KPIs (Time Saving >= 50%, Automation Coverage >= 70%). Now we have actual results to show instead.

---

## Slide-by-Slide Plan

### SECTION 1: CONTEXT (Slides 1-5)
*Targets: "Slides" criterion — structure, topic definition, background*

---

### Slide 1 — Title

**VizShifter: AI-Powered QlikView to Power BI Migration**

- Subtitle: DATA7902 Capstone Project
- Catherine Varas | May 2026
- Keep dark city background + purple branding from previous deck
- Update: name changed from "Migration Tool Qlik to Fabric" to match thesis title

---

### Slide 2 — Agenda (NEW)

*Adds the "excellent structure" the rubric explicitly requires.*

Numbered roadmap with icons:

1. The Problem
2. Solution & Architecture
3. Data Science Techniques
4. Results & Demo
5. Conclusions

Visual: clean timeline or numbered vertical list, one icon per section, minimal text.

---

### Slide 3 — The Problem: Why Migrate?

*Refine previous slide 3 — keep the 3-card layout (it was strong).*

| Card | Content |
|------|---------|
| QlikView Legacy Challenge | No cloud features, high maintenance cost, limited collaboration, declining talent pool |
| Manual Migration Pain | 18-34 hours per report, dual expertise required (QVS + DAX), risk of logic loss |
| Market Trend | Fabric adoption growing, unified Microsoft 365 licensing, AI-native platform |

Keep the Qlik → Fabric arrow icon. Keep the 3-card horizontal layout.

---

### Slide 4 — Gaps in Current Tools

*Keep previous slide 4 exactly as-is — it was already strong.*

Four quadrants:
- **Fragmented:** Qlik2PowerBI automates metadata extraction but can't handle logic
- **Labour-intensive:** Still rebuild dashboards manually, weeks per report
- **Error-prone:** Qlik2DAX / Power BI Helper mis-translate complex expressions
- **Hard to scale:** Enterprise projects require multiple scripts and tools

This provides the "appropriate background material" the rubric asks for.

---

### Slide 5 — Research Question & Scope (NEW)

*Critical for rubric: "Clearly defined topic and scope."*
*Aligns with thesis Section 1.2 and 1.4 (docs/thesis_project_description.md).*

**Research Question:**
> Can an AI-augmented pipeline automate QlikView → Power BI migration while preserving semantic fidelity?

**Scope:**
- **In scope:** Metadata extraction, code translation (QVS→M Query, Expressions→DAX), layout documentation, complexity assessment
- **Data:** 9 QlikView reports (.qvw) — Airline Operations textbook dataset
- **Out of scope:** Direct .pbix file generation, real-time data migration, production deployment

Visual: Clean text layout with a scope boundary diagram or in/out box.

---

### SECTION 2: SOLUTION & DATA SCIENCE (Slides 6-10)
*Targets: "Excellence, Innovation" criterion (35% of grade)*

---

### Slide 6 — VizShifter: Solution Overview

*Refine previous slide 6 — shorter text, updated screenshot.*

**Left side** — 4 bullet summary:
- End-to-end automated pipeline (8 steps)
- AI-powered code translation (RAG + GPT-4o)
- Quantitative migration complexity scoring
- Cloud-deployable web platform (Streamlit)

**Right side** — Updated screenshot of Streamlit UI showing:
- New dark purple theme
- Complexity Analysis tab visible in sidebar
- Pipeline execution view

---

### Slide 7 — Pipeline Architecture

*Update previous slide 7 — show all 8 steps instead of 3 modules.*
*Aligns with thesis Section 3.1 and docs/pipeline.md Section 2.*

Horizontal pipeline flow diagram with 8 numbered steps:

```
.qvw → [1] Metadata    → [2] XML      → [3] Field     → [4] M Query
        Extraction        Parsing        Mapping         (RAG+LLM)
        (GUI auto)        (xmltodict)    (type infer)    
                                                          ↓
       [8] Complexity  ← [7] Output   ← [6] Report    ← [5] DAX
        Scoring           Analysis       Pages           Translation
        (feature eng.)    (JSON)         (PDF/PNG)       (LLM+context)
```

Color-code by technique type:
- Blue: Automation (Steps 1-3, 6-7)
- Purple: AI/LLM (Steps 4-5)
- Green: Data Science (Step 8)

Show input (.qvw) on left, outputs (Power BI artefacts + complexity score) on right.

---

### Slide 8 — Data Science Technique 1: RAG for Script Translation (NEW)

*THE key innovation slide. Aligns with thesis Section 4.4 and pipeline.md Section 3.4.*
*This slide alone can make or break the 35% Innovation score.*

**Title:** "Retrieval-Augmented Generation for M Query Translation"

**Left — RAG Pipeline Diagram:**

```
QVS Load Script
      ↓
   Chunk & Embed (text-embedding-3-small)
      ↓
   Vector Store ← M Query Documentation (chunked & embedded)
      ↓
   Cosine Similarity → Top-k similar examples
      ↓
   Few-shot Prompt Assembly
      ↓
   GPT-4o → M Query Output
```

**Right — Before/After Comparison:**

| Approach | Input (QVS) | Output |
|----------|-------------|--------|
| Zero-shot (no RAG) | `LOAD * FROM [data.qvd]` | Generic/incorrect M syntax |
| **RAG-augmented** | `LOAD * FROM [data.qvd]` | Correct `let Source = Csv.Document(...)` |

**Bottom callout:** "RAG grounds translations in verified M Query patterns, reducing LLM hallucination"

*Ref: Lewis et al. (2020) — Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*

---

### Slide 9 — Data Science Technique 2: Semantic DAX Translation (NEW)

*Aligns with thesis Section 4.5 and pipeline.md Section 3.5.*

**Title:** "Context-Aware Expression Translation"

**3-step process diagram:**

```
Step 1: Field Type Inference
   fields.csv → $numeric, $key, $text tags
   → Auto-detect measures vs. dimensions

Step 2: Semantic Model Injection
   Build context: table names + field types + relationships
   → Inject into LLM prompt as system context

Step 3: Guided Translation
   Expression + Semantic Context → GPT-4o → DAX
```

**Example box:**
- **QlikView:** `Sum({<Year={$(vCurrentYear)}>} Revenue)`
- **Context injected:** Revenue = numeric measure, Year = dimension, vCurrentYear = variable
- **DAX:** `Total Revenue = CALCULATE(SUM('Sales'[Revenue]), FILTER(ALL('Date'[Year]), 'Date'[Year] = [CurrentYear]))`

**Callout:** "Set analysis has no direct DAX equivalent — requires semantic understanding, not string replacement"

---

### Slide 10 — Data Science Technique 3: Complexity Scoring (NEW)

*Aligns with thesis Section 4.8 and complexity.py module.*

**Title:** "Migration Complexity Analysis: Feature Engineering"

**Left — Algorithm summary:**
- 27 features extracted from 7 data files
- 4 dimensions with domain-expert weights
- Min-max normalisation with predefined reference ranges
- Two-level weighted aggregation → composite score 0-100
- Classification: Low / Medium / High / Critical

**Center — Dimension weights (pie or bar chart):**

| Dimension | Weight | Key Features |
|-----------|--------|-------------|
| Data Model | 30% | fields, keys, cardinality, multi-table fields |
| Expressions | 25% | count, set analysis, nesting depth, DAX gap |
| Script | 25% | LOADs, JOINs, loops, subroutines |
| Layout | 20% | objects, sheets, charts, dimensions |

**Right — Demo result:**
- Score: **22.9 / 100 → Low Complexity**
- Bar chart: Data Model 45, Layout 27, Script 11, Expressions 4
- Estimated effort: 1-3 person-days

**Bottom:** "Follows McCabe (1976) / Halstead (1977) tradition — predefined ranges, works with N=1"

---

### SECTION 3: RESULTS & DEMO (Slides 11-14)
*Targets: "Completeness" criterion (30% of grade)*

---

### Slide 11 — Live Demo / Platform Screenshots (NEW)

*Presenter pauses here to show Streamlit Cloud or screenshots.*

Option A (live demo): Title "Live Demo" + Streamlit Cloud URL, switch to browser.

Option B (screenshots): 4 annotated screenshots in grid:
1. **Pipeline Execution** — Main App with step controls
2. **DAX & M Query Results** — translated expressions view
3. **Complexity Dashboard** — score, dimensions, recommendations
4. **Report Pages** — generated PNG layouts

Speaker note: Have backup screenshots ready in case of network issues.

---

### Slide 12 — Quantitative Results (NEW)

*Must show measurable outcomes. Rubric: "self-evident that the work is complete and correct."*

**Comparison table:**

| Metric | Manual Migration | VizShifter |
|--------|-----------------|------------|
| Time per report | 18-34 hours | ~15 minutes |
| Expression coverage | Manual review | 100% extracted, ~85% auto-translated |
| M Query generation | Manual rewrite | Automated via RAG |
| Layout documentation | Manual screenshots | Auto-generated PDF |
| Complexity assessment | Subjective estimate | Quantitative 0-100 score |
| Scalability | 1 report at a time | Batch pipeline |

**KPI callout boxes:**
- Time Reduction: **>95%** for initial analysis phase
- Reports Processed: 9 QVW files
- Measures Translated: 83 expressions

---

### Slide 13 — Translation Examples (NEW)

*Concrete evidence the system works.*

**Side-by-side examples:**

**QVS → M Query:**
```
-- QlikView Script:                    -- M Query Output:
LOAD                                   let
  FlightId,                              Source = Csv.Document(...),
  AirlineCode,                           #"Changed Type" = Table.TransformColumnTypes(
  Revenue                                  Source, {{"FlightId", Int64.Type},
FROM [airline_data.qvd] (qvd);            {"AirlineCode", type text},
                                            {"Revenue", type number}})
                                        in #"Changed Type"
```

**Expression → DAX:**
| QlikView Expression | DAX Translation |
|-------------------|-----------------|
| `Sum(Revenue)` | `Total Revenue = SUM('Flights'[Revenue])` |
| `Count(DISTINCT FlightId)` | `Unique Flights = DISTINCTCOUNT('Flights'[FlightId])` |
| `Avg(Passengers)` | `Avg Passengers = AVERAGE('Flights'[Passengers])` |

**Stats:** "8/8 expressions successfully translated for demo report (Chapter 3)"

---

### Slide 14 — Exploratory Analysis

*Merge best visuals from previous slides 8 and 9.*

**Left:** Objects by File bar chart (shows heterogeneous complexity: 9-105 objects per file)

**Right top:** KPI metrics row:
- 14 Tables Discovered
- 14 Sheets Scanned
- 105 Objects Extracted
- 83 Measures Translated

**Right bottom:** Most Used Tables chart or Objects by SheetName chart

**Callout:** "9 .qvw files → 71 sheets, 15 tables, 98 fields identified"

---

### SECTION 4: CLOSURE (Slides 15-16)

---

### Slide 15 — Conclusions & Future Work

*Refine previous slide 11. Aligns with thesis Section 7.*

**5 Key Contributions:**
1. End-to-end automated 8-step migration pipeline
2. RAG-based M Query translation (novel application of retrieval-augmented generation to BI code)
3. Context-aware DAX translation with semantic model inference
4. Quantitative complexity scoring via feature engineering (27 features, 4 dimensions)
5. Cloud-deployable web platform for non-technical users

**Limitations (honest assessment):**
- Single dataset (textbook reports) — needs enterprise-scale validation
- DAX translation quality depends on LLM — human review still required
- No direct .pbix file generation yet

**Future Work:**
- Expand RAG corpus with enterprise migration examples
- Add .pbix auto-generation via Power BI REST API
- Calibrate complexity scores against actual migration times

---

### Slide 16 — Thank You / Q&A

- "Thank You — Questions?"
- Catherine Varas
- GitHub repository URL
- Streamlit Cloud demo URL
- Purple gradient background (same style as previous deck)

---

## Q&A Preparation

*Supports "Presentation" criterion (20%) — handle questions masterfully.*

| Likely Question | Suggested Answer |
|----------------|------------------|
| "How accurate are the DAX translations?" | 8/8 for demo dataset. ~85% for common patterns. Human review recommended for complex set analysis edge cases. |
| "Why not use existing tools like Qlik2PowerBI?" | Those handle metadata extraction only — can't translate logic (expressions→DAX, scripts→M Query). VizShifter bridges that gap with AI. |
| "How does the complexity score compare to manual estimates?" | Follows McCabe/Halstead tradition with predefined ranges. Enterprise validation against actual migration times would strengthen calibration. |
| "What about very complex QlikView files (set analysis, loops)?" | Complexity scorer flags them as High/Critical. DAX translator handles set analysis but flags loops/subroutines as needing manual rewrite — no direct M Query equivalent. |
| "Could this work for other BI platforms (Tableau, SSRS)?" | Architecture is modular — extraction is QlikView-specific, but RAG translation and complexity scoring patterns are adaptable to other source platforms. |
| "What was the most challenging part?" | UTF-16 encoding in QlikView files and the lack of any API for DocumentAnalyzer — had to build GUI automation with template matching and encoding fallback chains. |
| "How does RAG compare to fine-tuning?" | RAG is more practical: no training data needed, knowledge base is updatable without retraining, and it works with any LLM. Fine-tuning would require thousands of QVS↔M Query pairs that don't exist publicly. |

---

## Visual Design Guidelines

Maintain consistency with previous deck:
- **Primary color:** Purple (#7c3aed)
- **Background:** Dark (for slides with screenshots) or white (for diagram slides)
- **Fonts:** Bold sans-serif for titles, clean sans-serif for body
- **Layout:** Maximum 3-4 key points per slide, use diagrams/tables instead of bullets
- **Footer:** "Catherine Varas" on every slide
- **Icons:** Use Bootstrap Icons or similar (consistent with Streamlit sidebar icons)

---

## Cross-Reference with Project Documentation

| Slide | Thesis Section (docs/thesis_project_description.md) | Pipeline Doc (docs/pipeline.md) |
|-------|-----------------------------------------------------|--------------------------------|
| 3. The Problem | 1.1 Contexto y Motivación | 1. Overview |
| 4. Tool Gaps | 1.1 (migration challenges) | — |
| 5. Research Question | 1.2 Problema de Investigación, 1.4 Alcance | — |
| 7. Architecture | 3.1 Arquitectura General | 2. Pipeline Architecture |
| 8. RAG Translation | 2.3 RAG, 4.4 Etapa 4 | 3.4 Step 4 |
| 9. Semantic DAX | 4.5 Etapa 5 | 3.5 Step 5 |
| 10. Complexity | 4.8 Análisis de Complejidad | 3.8 Step 8 |
| 12. Results | 5. Resultados | — |
| 15. Conclusions | 7. Conclusiones | 6. Data Science Contributions |
