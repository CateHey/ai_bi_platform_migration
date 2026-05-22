# QlikView to Power BI Automated Migration Pipeline

## 1. Overview

This project implements an end-to-end automated pipeline that migrates QlikView business intelligence reports to Microsoft Power BI / Fabric. The pipeline extracts metadata from legacy QlikView `.qvw` files, translates load scripts into Power Query (M) language, and converts QlikView expressions into DAX measures.

The system combines traditional software automation (GUI control, XML parsing, file-system orchestration) with LLM-based code translation (Retrieval-Augmented Generation, prompt engineering) to address a real-world enterprise migration challenge that currently requires significant manual effort.

---

## 2. Pipeline Architecture

The pipeline consists of six sequential steps, each producing intermediate artefacts consumed by downstream stages:

```
.qvw (QlikView file)
  |
  +---> [Step 1] Metadata Extraction      --> XML descriptors + CSV tables
  |       (GUI automation via pyautogui)
  |
  +---> [Step 2] XML Parsing              --> Flattened CSVs (one per object)
  |       (xmltodict + recursive flatten)
  |
  +---> [Step 3] Field Mapping            --> Filtered attribute/value CSVs
  |       (lookup table from field_mapping.csv)
  |
  +---> [Step 4] Data Source Creation      --> M Query scripts (Power Query)
  |       (RAG + GPT-4o)
  |
  +---> [Step 5] Expression to DAX        --> DAX measures
  |       (semantic model context + GPT-4o)
  |
  +---> [Step 6] Output Analysis           --> Unified enriched JSON
          (multi-source data integration)
```

---

## 3. Step-by-Step Technical Description

### 3.1 Step 1 -- Metadata Extraction

**Purpose:** Extract all internal metadata from QlikView documents by driving the proprietary DocumentAnalyzer tool through GUI automation.

**Techniques:**
- **GUI automation** using `pyautogui` and `pygetwindow`: the pipeline opens DocumentAnalyzer (itself a `.qvw` application), types file paths, clicks buttons, and handles dialog boxes programmatically.
- **Image recognition** with template matching (`locateCenterOnScreen`, confidence=0.8) for resolution-independent button detection, with fallback to hardcoded pixel coordinates.
- **Incremental processing** via SHA-256 file hashing: only files that have changed since the last run are re-processed, avoiding redundant GUI automation cycles.
- **Window reuse**: after the first file, the QlikView window is kept open to save ~10 seconds per subsequent file.

**Input:** `.qvw` files from the source directory.

**Output per report:**

| File | Description |
|------|-------------|
| `objects.csv` | All visual objects (charts, listboxes, buttons, etc.) |
| `objectSheets.csv` | Object-to-sheet assignment mapping |
| `sheets.csv` | Sheet definitions (SheetId, SheetName) |
| `expressions.csv` | QlikView expressions per object |
| `fields.csv` | Field metadata (name, tags, data type) |
| `script.qvs` | Full QlikView load script |
| `Document/*.xml` | One XML descriptor per visual object (e.g., `LB01.xml`, `CH01.xml`) |

---

### 3.2 Step 2 -- XML Parsing

**Purpose:** Parse QlikView's internal XML object descriptors into structured, flat CSV files suitable for analysis.

**Techniques:**
- **XML deserialization** using `xmltodict` to convert nested XML into Python dictionaries.
- **Recursive dictionary flattening** via depth-first traversal: nested structures are collapsed into single-level dictionaries with composite keys separated by underscores (e.g., `ListBoxProperties_Layout_Frame_Rect_Left`). Array elements receive indexed suffixes (e.g., `ContainerItemDef[0]_Id`).
- **Encoding detection** using `chardet` to handle QlikView's mixed encoding outputs (UTF-16, Latin-1, UTF-8).
- **Field frequency analysis**: a `defaultdict(set)` tracks which XML attributes appear across all objects, producing a global field-occurrence report.

**Input:** XML files in `Document/` subdirectories.

**Output:**
- Per-object flat CSV (e.g., `LB01.csv` -- one row, ~200 columns)
- `objects_all_fields.csv` -- hierarchical field breakdown with occurrence counts and percentages

---

### 3.3 Step 3 -- Field Mapping

**Purpose:** Filter each flattened object CSV to retain only the attributes semantically relevant for Power BI migration, using a predefined mapping table.

**Techniques:**
- **Lookup table** (`field_mapping.csv`, 93 entries): maps QlikView two-character object prefixes to Power BI equivalents and lists the specific XML properties to preserve.
- **Pivot transformation**: wide-format CSVs (many columns) are pivoted into tall-format attribute/value pairs for downstream JSON assembly.

**Mapping examples:**

| QlikView Prefix | QlikView Type | Power BI Equivalent | Preserved Fields |
|-----------------|---------------|---------------------|-----------------|
| CH | Chart | Visualization | Position, size, title, chart type, measure, dimension |
| LB | ListBox | Slicer | Position, size, dimension name |
| TB | Table Box | Table | Position, size, title, fields |
| SB | Statistics Box | Card / KPI | Position, size, title, expression |
| TX | Text Object | Text Box | Position, size, text content |

**Input:** Flat CSVs from Step 2 + `field_mapping.csv`.

**Output:** `{object}_mapped_pivoted.csv` per object -- filtered to only migration-relevant attributes.

---

### 3.4 Step 4 -- Data Source Creation (M Query Generation)

**Purpose:** Translate QlikView load scripts (`.qvs`) into Power BI M Query (Power Query) code using an LLM with Retrieval-Augmented Generation.

**Techniques:**

1. **Script segmentation**: regex-based tab splitting divides multi-tab QlikView scripts into independent units for parallel translation.

2. **Retrieval-Augmented Generation (RAG)**:
   - A knowledge base of QlikView-to-M-Query translation examples is embedded using OpenAI's `text-embedding-3-small` model.
   - At translation time, the current script segment is embedded and compared against the knowledge base via **cosine similarity**.
   - The top-k most similar examples are retrieved and injected into the LLM prompt as few-shot demonstrations.
   - The embedding index is persisted as `embedding_index.json` for reuse across runs.

3. **LLM translation**:
   - Model: Azure OpenAI `gpt-4o`, temperature 0.5.
   - System prompt defines the role and output format (structured table blocks).
   - Handles specific QlikView constructs: `LOAD`, `SQL SELECT`, `RESIDENT`, `INLINE`, `JOIN`, `MAP`, `APPLYMAP`.

4. **Post-processing**: regex extraction of table blocks from LLM output, parsed into structured `(TableName, MQueryScript)` pairs.

**Input:** `script.qvs` files (UTF-16 encoded).

**Output:** `m_query_output.csv` -- one row per Power Query table with columns `TableName` and `MQueryScript`.

---

### 3.5 Step 5 -- Expression to DAX Translation

**Purpose:** Translate QlikView visual expressions (aggregations, calculations, conditional formatting) into DAX measures for Power BI.

**Techniques:**

1. **Semantic model extraction**: reads `fields.csv` to build a contextual schema:
   - Groups fields by source table name.
   - Infers field data types from QlikView tags (`$numeric` -> Whole Number, `$date` -> DateTime, `$key` -> Text, etc.).
   - Identifies potential join keys (fields appearing in multiple tables).

2. **LLM-based translation**:
   - Model: Azure OpenAI `gpt-4o`, temperature 0.3 (lower than Step 4 for higher consistency).
   - Each expression is translated individually with its full field metadata context.
   - The model flags low-confidence translations for manual review.

3. **Rate limiting**: implements a sliding-window RPM throttle (150 requests/minute) using a deque of timestamps, with automatic backoff when the limit is approached.

4. **Resource tracking**: logs total tokens consumed, successful/failed request counts, and total duration.

**Input:** `expressions.csv` + `fields.csv` per report.

**Output:**
- `expressions_with_dax.csv` -- original expression columns plus a new `DAX` column
- `DAX_output.csv` -- clean DAX formulas only

---

### 3.6 Step 6 -- Output Analysis (Structured JSON Assembly)

**Purpose:** Synthesize all intermediate outputs from Steps 1-5 into unified, enriched JSON files suitable for downstream validation and Power BI report construction.

**Techniques:**
- **Multi-source data integration**: loads up to 9 CSV sources and performs SQL-like joins using pandas `merge()`:
  1. `objectSheets x sheets` -> adds sheet names to objects
  2. `objects x (objectSheets + sheets)` -> full object context with sheet assignment
  3. Add field mapping: Power BI object type for each QlikView type
  4. Attach expressions and DAX measures grouped by ObjectId

- **Graceful degradation**: if any source file is missing (e.g., DAX not yet generated), the function still processes everything available and reports what was skipped.

**Input:** All CSV outputs from prior steps.

**Output in `Outputanalysis/`:**
- `enriched_dax.json` -- objects enriched with sheet names, PBI types, and DAX expressions
- `m_query_output.json` -- M Query scripts in JSON format

---

## 4. Technologies and Libraries

| Category | Technologies |
|----------|-------------|
| **Language** | Python 3.11+ |
| **Web UI** | Streamlit (interactive dashboard with step selection, monitoring, results viewer) |
| **AI/LLM** | Azure OpenAI GPT-4o (chat completions), text-embedding-3-small |
| **GUI Automation** | pyautogui, pygetwindow |
| **Data Processing** | pandas, xmltodict, chardet, csv, json |
| **Embeddings/RAG** | OpenAI embeddings + cosine similarity (numpy) |

---

### 3.7 Step 7 -- Migration Complexity Analysis

**Purpose:** Quantitatively assess the complexity of each QlikView report to estimate migration effort and prioritise reports for migration.

**Techniques:**

1. **Feature engineering**: 27 quantitative features extracted from 7 data sources across four analytical dimensions:
   - **Data Model (30%)**: field count, key field count, measure field count, average cardinality, multi-table fields, type diversity.
   - **Expressions (25%)**: expression count, average length, set analysis presence, nesting depth, aggregation diversity, DAX translation gap.
   - **Script (25%)**: line count, LOAD/JOIN/RESIDENT counts, subroutine and loop presence, tab count.
   - **Layout (20%)**: object count, sheet count, max objects per sheet, unique object types, chart count, dimension count.

2. **Min-max normalisation with predefined reference ranges**: unlike data-driven normalisation (z-score, percentiles), reference ranges are defined from domain knowledge of QlikView migration projects. This enables valid scoring with a single report (N=1), following the approach of software complexity indices (McCabe, 1976; Halstead, 1977).

3. **Two-level weighted aggregation**: features are combined within each dimension using intra-category weights, then dimensions are combined using inter-category weights to produce an overall score (0-100).

4. **Classification and effort estimation**: scores are classified into Low (<25), Medium (25-50), High (50-75), and Critical (>75), with person-day estimates per tier.

5. **Contextual recommendations**: rules-based recommendation generation identifies specific risk factors (JOINs, loops, subroutines, dense layouts) and suggests mitigation strategies.

**Input:** All CSV outputs from Steps 1-6.

**Output:** Complexity report with overall score, dimension scores, feature breakdown, classification, effort estimate, and recommendations.

---

## 5. Critical Analysis: Alignment with Learning Outcomes

> **Note:** This section is written as a self-critical assessment. A Master's examiner would probe the distinction between *using AI tools* and *implementing data science algorithms*. The analysis below is honest about where the project is strong and where it has gaps.

### LO1 -- Synthesise information from a variety of sources to develop informed solutions

**Assessment: STRONG FIT**

The pipeline genuinely synthesises information from multiple heterogeneous sources:

- **QlikView internal metadata** (XML object descriptors, CSV tables, load scripts) -- extracted via GUI automation since QlikView provides no API.
- **Domain knowledge bases** (field mapping tables, RAG example corpora) -- curated translation references that ground LLM outputs in domain-specific patterns.
- **AI model outputs** (LLM-generated M Query code, DAX measures) -- synthesised with structural metadata to produce validated migration artefacts.
The Output Analysis step (Step 6) exemplifies this synthesis: it joins up to 9 distinct data sources through a series of relational operations to produce a unified enriched representation that no single source could provide alone.

**This LO is well-supported.** The pipeline addresses a real integration challenge across incompatible data formats.

---

### LO2 -- Implement a data science approach to solving a problem within a given application context

**Assessment: WEAK FIT -- requires critical discussion**

The project follows a structured *engineering methodology*, but an examiner may challenge whether it constitutes a *data science approach*:

| Claimed | Honest Assessment |
|---------|-------------------|
| Problem formulation as multi-modal translation | Valid framing, but translation is delegated entirely to GPT-4o -- the student does not design or train any model |
| Data acquisition via automated extraction | This is **software engineering** (GUI automation, XML parsing), not data science |
| Feature engineering (XML flattening, field mapping) | This is **data wrangling** -- necessary but not sufficient for data science |
| Model application (RAG + GPT-4o) | The "model" is a pre-trained commercial API. The RAG implementation is a 4-line cosine similarity function calling OpenAI's embedding API |
| Iterative refinement | Hash-based caching is an engineering optimisation, not a data science technique |

**The core issue:** the project *consumes* AI outputs but does not *produce* data science. Calling GPT-4o to translate code is analogous to using Google Translate in a linguistics thesis -- it demonstrates application integration, not methodology.

**What would strengthen this LO:** implementing measurable evaluation of the LLM outputs (BLEU/ROUGE scores, AST-based comparison, human evaluation framework), or training a custom model component rather than relying entirely on commercial APIs.

---

### LO3 -- Apply, optimise and evaluate appropriate data science techniques

**Assessment: WEAK FIT -- the most vulnerable LO**

**Techniques claimed vs. reality:**

| Claimed Technique | What Actually Happens | Classification |
|-------------------|----------------------|----------------|
| Retrieval-Augmented Generation (RAG) | OpenAI embedding API + 4-line numpy cosine similarity + prompt concatenation | API integration + basic linear algebra |
| Prompt engineering | Hand-written system prompts with role assignment and output format constraints | Software engineering (no systematic optimisation or evaluation) |
| Temperature tuning | Two hardcoded temperature values (0.5 for M Query, 0.3 for DAX) chosen without empirical comparison | Engineering judgment, not optimisation |
| Rate limiting | Sliding-window timestamp deque | Pure software engineering |
| Incremental processing | SHA-256 file hashing | Pure software engineering |

**What is missing for a Master's level:**
- **No ML algorithms**: zero sklearn, zero pytorch, zero model training anywhere in the codebase
- **No evaluation metrics**: no BLEU, ROUGE, precision, recall, F1, confusion matrix, or any quantitative evaluation of translation quality
- **No statistical analysis**: no hypothesis testing, no confidence intervals, no significance tests
- **No data mining**: no clustering, classification, regression, association rules, or anomaly detection
- **No optimisation**: temperature values are not empirically tuned (no A/B testing, no grid search, no ablation study)
- **No comparison baselines**: RAG vs. zero-shot vs. few-shot is never measured

**An examiner would note:** "You used GPT-4o effectively, but where is the data science? Where are the algorithms? Where is the evaluation?"

---

### LO4 -- Present project outcomes with compelling arguments and appropriate use of visual aids

**Assessment: MODERATE FIT**

The Streamlit dashboard serves as the presentation layer:

- **Interactive step selector**: users can run individual steps or the full pipeline, with real-time status updates.
- **Visual results viewer**: DAX expressions displayed as syntax-highlighted code blocks, M Queries in expandable panels, report pages as full-width image galleries.
- **Execution history**: per-file status indicators (success/failed/skipped) with timestamps and error details.
- **Pipeline Info page**: in-app documentation with architecture diagram and step-by-step descriptions.

The pipeline also generates structured JSON outputs (`enriched_dax.json`, `m_query_output.json`) that can feed into external visualisation tools or reports.

**What would strengthen this LO:** charts showing translation quality metrics over multiple runs, comparative visualisations (RAG vs. baseline), confusion matrices for expression type classification.

---

### LO5 -- Write a technical project report with clear description of problem, motivation, methodology and findings

**Assessment: MODERATE FIT**

The pipeline provides artefacts that support technical reporting:

- **Problem**: manual QlikView-to-Power-BI migration is time-consuming, error-prone, and does not scale.
- **Motivation**: organisations face hundreds of reports with thousands of expressions that must be faithfully translated.
- **Methodology**: a six-step pipeline that decomposes migration into tractable sub-problems.

**Gap:** the "findings" are currently limited to success/failure counts per step. There are no quantitative findings about translation quality, no statistical analysis of results, and no empirical comparison of approaches. A Master's report requires measurable, reproducible findings -- not just "the pipeline ran successfully."

---

## 6. Data Science Contributions

### 6.1 Migration Complexity Analysis (Implemented)

Step 8 introduces a quantitative feature engineering and multi-criteria scoring system:
- **27 features** extracted from 7 heterogeneous data sources via regex, pandas aggregation, and statistical analysis
- **Min-max normalisation** with domain-specific predefined reference ranges (following McCabe/Halstead tradition)
- **Two-level weighted aggregation** producing a composite complexity index (0-100)
- **Rule-based classification** into effort tiers with contextual recommendation generation

This module is deterministic, reproducible, and does not depend on external APIs.

### 6.2 RAG Pipeline for Code Translation (Implemented)

Step 4 implements a practical Retrieval-Augmented Generation system:
- **Embedding-based similarity search** using text-embedding-3-small (1536 dimensions) + cosine similarity
- **Few-shot learning** via retrieved domain-specific examples injected into LLM prompts
- **Knowledge base construction** with persistent embedding index

### 6.3 Semantic Model Inference (Implemented)

Step 5 extracts a data model schema from metadata:
- **Heuristic type inference** from QlikView field tags ($key, $numeric, $date → DAX types)
- **Relationship discovery** via multi-table field analysis (FieldTableCount > 1)
- **Schema context injection** enabling semantically-aware LLM translations

### 6.4 Potential Extensions

The following additions could further strengthen the data science component:
- **Translation quality evaluation**: BLEU/CodeBLEU scores, ablation studies (RAG vs. zero-shot)
- **Object clustering**: unsupervised grouping of QlikView objects via K-Means on extracted features
- **Expression complexity prediction**: supervised classification to predict DAX translation difficulty

---

## 7. Proposals to Strengthen the Data Science Component

The following are concrete, implementable additions that would transform the project from "software engineering with LLM APIs" into a genuine data science contribution. They are ordered by impact and feasibility.

### Proposal A: Translation Quality Evaluation Framework (HIGH PRIORITY)

**What:** Build a systematic evaluation pipeline for the LLM-generated DAX and M Query translations.

**How:**
1. Create a **gold-standard dataset**: manually translate 30-50 expressions/scripts and validate them as correct DAX/M Query.
2. Compute **code similarity metrics**: BLEU score, CodeBLEU (structure-aware), Levenshtein edit distance, token-level precision/recall.
3. Implement **AST-based comparison**: parse both generated and reference DAX into abstract syntax trees and measure structural similarity.
4. Run **ablation studies**: compare RAG+GPT-4o vs. zero-shot GPT-4o vs. few-shot (fixed examples) vs. GPT-4o-mini. Measure quality differences with statistical significance tests (paired t-test or Wilcoxon signed-rank).
5. Visualise results: box plots of BLEU scores per approach, confusion matrix of expression types (correct/incorrect/partial), error categorisation.

**Why this matters:** This turns "we used GPT-4o" into "we measured that RAG improves translation quality by X% (p < 0.05) compared to zero-shot, with the largest gains on JOIN constructs." That is a defensible finding.

**Libraries:** `nltk` (BLEU), `sacrebleu`, `scipy.stats` (significance tests), `sklearn.metrics` (confusion matrix).

### Proposal B: QlikView Object Clustering and Migration Pattern Discovery (HIGH PRIORITY)

**What:** Apply unsupervised learning to discover natural groupings of QlikView objects and identify migration patterns.

**How:**
1. **Feature extraction** from flattened XML CSVs: object type, property count, expression complexity (nesting depth, function count), position/size, number of dimensions/measures.
2. **Clustering**: apply K-Means and DBSCAN to the feature space. Use silhouette score and elbow method to select optimal k.
3. **Dimensionality reduction**: visualise clusters using PCA or t-SNE in 2D scatter plots.
4. **Pattern discovery**: analyse cluster composition -- do complex charts cluster together? Do simple listboxes form a distinct group? Which clusters have the highest translation failure rates?
5. **Practical application**: use cluster membership to predict migration difficulty (easy/medium/hard) and estimate effort per report.

**Why this matters:** This is genuine data mining -- discovering structure in the QlikView metadata that was not known a priori. It directly addresses LO2 and LO3.

**Libraries:** `sklearn.cluster`, `sklearn.decomposition`, `sklearn.metrics` (silhouette), `matplotlib`/`plotly`.

### Proposal C: Expression Complexity Prediction Model (MEDIUM PRIORITY)

**What:** Train a supervised model to predict which expressions will fail or produce low-confidence DAX translations, *before* calling the LLM.

**How:**
1. **Label dataset**: after running Step 5, label each expression as correct/incorrect/partial (manual review or automated syntax check).
2. **Feature engineering**: expression length, nesting depth, number of QlikView-specific functions (`APPLYMAP`, `AGGR`, `SET`), number of field references, presence of conditional logic.
3. **Train classifiers**: logistic regression, random forest, gradient boosting (XGBoost). Use 5-fold cross-validation.
4. **Evaluate**: precision, recall, F1, ROC-AUC. Report feature importances -- which expression characteristics predict failure?
5. **Apply**: flag high-risk expressions before LLM translation, enabling targeted manual review.

**Why this matters:** This is a genuine ML classification problem with practical utility. It demonstrates the full train/evaluate/deploy cycle expected in a Master's thesis.

**Libraries:** `sklearn`, `xgboost`, `matplotlib` (ROC curves, feature importance plots).

### Proposal D: Automatic Semantic Model Generation (HIGH PRIORITY)

**What:** Automatically infer and generate the Power BI semantic model (tables, relationships, hierarchies) from the QlikView metadata, using graph algorithms and heuristic classification.

**How:**
1. **Table role classification**: parse `fields.csv` to classify each table as **fact** or **dimension** using heuristics:
   - Tables with high-cardinality numeric fields and few join keys → fact tables.
   - Tables with low-cardinality categorical fields and a single primary key → dimension tables.
   - Validate with a decision tree classifier trained on labelled examples.
2. **Relationship inference**: fields with `FieldTableCount > 1` (appearing in multiple tables) are join keys. Fields with the `%` prefix in `script.qvs` are explicit foreign keys. Build a **directed graph** (networkx DiGraph) where nodes are tables and edges are join relationships with cardinality annotations (one-to-many, many-to-one).
3. **Hierarchy detection**: analyse dimension fields to discover natural roll-up hierarchies:
   - Parse field names and cardinalities: `Year (3 values) → Quarter (12) → Month (36)` implies a time hierarchy.
   - Use **association rule mining** (support/confidence) on field co-occurrence in expressions to detect drill-down paths.
4. **Star schema validation**: apply graph-theoretic checks -- a valid star schema has exactly one fact node with degree equal to the number of dimensions, and no dimension-to-dimension edges.
5. **Visual output**: generate an **ER diagram** using `graphviz` or `networkx` + `matplotlib`, annotated with cardinalities, data types, and hierarchy levels. Render in Streamlit with `st.graphviz_chart()`.
6. **Export**: produce a `semantic_model.json` file that Power BI's TMDL/TMSL can consume, automating relationship creation.

**Why this matters:** This is genuine **graph-based data mining** applied to metadata. It produces a tangible, useful artefact (the Power BI data model) that no other step provides. The star schema inference is a novel application of graph analysis to BI migration. It directly addresses LO1 (multi-source synthesis), LO2 (data science methodology), and LO3 (graph algorithms + classification).

**Available data:**
- `fields.csv`: FieldName, FieldTableCount, FieldValueCount, FieldTables, FieldTags (`$key`, `$numeric`, `$date`, `$text`)
- `script.qvs`: LOAD statements with explicit table names and QVD source files
- `dimensions.csv`: which fields are used as dimensions in charts

**Libraries:** `networkx` (graph construction, analysis), `graphviz` (ER diagram rendering), `sklearn` (decision tree for table classification), `mlxtend` (association rules for hierarchy detection).

### Proposal E: Data Lineage Graph and Impact Analysis (MEDIUM PRIORITY)

**What:** Parse QlikView load scripts to build a complete data lineage DAG (directed acyclic graph) from source files through transformations to visual objects.

**How:**
1. **Script parsing**: build a regex/grammar-based parser for QlikView load scripts that extracts:
   - Source references (`FROM *.qvd`, `RESIDENT`, `INLINE`)
   - Table creation/renaming (`LOAD ... AS`, `RENAME TABLE`)
   - Field transformations (`LEFT JOIN`, `CONCATENATE`, `APPLYMAP`)
   - Variable assignments (`SET`, `LET`)
2. **DAG construction**: build a directed graph where:
   - **Source nodes**: QVD files, database connections, inline data
   - **Transformation nodes**: LOAD statements with their operations
   - **Table nodes**: resulting in-memory tables
   - **Visual nodes**: charts/objects that consume the tables (linked via `expressions.csv` and `dimensions.csv`)
3. **Impact analysis**: for any given source field, trace forward through the DAG to find all affected expressions, DAX measures, and visual objects. Compute **field coverage** (% of source fields that reach at least one visual) and **orphan detection** (fields loaded but never used).
4. **Complexity metrics**: compute graph-theoretic measures per table:
   - In-degree (number of sources) and out-degree (number of consumers)
   - Longest path from source to visual (transformation depth)
   - Betweenness centrality (which tables are critical bottlenecks)
5. **Visualisation**: render the lineage DAG in Streamlit using `st.graphviz_chart()` or `pyvis` for interactive exploration.

**Why this matters:** Data lineage is a core data governance concern in enterprise migrations. Building it algorithmically from script parsing demonstrates NLP (custom parser), graph theory (DAG analysis, centrality), and practical utility. It helps answer "if I change this source table, what breaks downstream?" -- a question every migration team asks.

**Libraries:** `networkx` (DAG construction, centrality, path analysis), `graphviz`/`pyvis` (visualisation), `re` (script parsing).

### Proposal F: Load Script Pattern Mining with NLP (LOWER PRIORITY)

**What:** Apply NLP and pattern mining to QlikView load scripts to automatically classify transformation types and improve RAG retrieval.

**How:**
1. **Tokenise** QlikView scripts using a custom lexer (LOAD, SELECT, JOIN, WHERE, etc.).
2. **TF-IDF vectorisation** of script segments.
3. **Topic modelling** (LDA or NMF) to discover common script patterns (data loading, incremental updates, cross-table joins, inline data).
4. **Association rules**: mine frequent construct co-occurrences (e.g., "WHERE + RESIDENT" always appears with "DROP TABLE").
5. **Classification**: train a model to classify script segments by transformation type, enabling type-specific translation strategies and better RAG retrieval.

**Why this matters:** This applies genuine NLP/text mining to a novel corpus (QlikView scripting language). It could inform better RAG retrieval strategies by matching script segments to examples by transformation type rather than just embedding similarity.

**Libraries:** `sklearn.feature_extraction.text` (TF-IDF), `sklearn.decomposition` (NMF/LDA), `mlxtend` (association rules).

---

## 8. Recommended Minimum Scope Changes

For a defensible Master's thesis, implement **at least Proposals A and D**:

| Proposal | LOs Addressed | Effort | Impact |
|----------|---------------|--------|--------|
| **A: Evaluation Framework** | LO2, LO3, LO5 | 2-3 weeks | Critical -- turns anecdotal results into measurable findings |
| **B: Object Clustering** | LO2, LO3, LO4 | 1-2 weeks | High -- adds genuine data mining with visual outputs |
| **C: Complexity Prediction** | LO2, LO3 | 2 weeks | Medium -- adds supervised ML classification |
| **D: Semantic Model Generation** | LO1, LO2, LO3, LO4 | 2-3 weeks | Critical -- graph algorithms + classification + visual ER output + direct migration utility |
| **E: Data Lineage Graph** | LO1, LO3, LO4 | 2 weeks | High -- graph theory + NLP parsing + interactive visualisation |
| F: Script Pattern Mining | LO3 | 2 weeks | Lower -- NLP/text mining addition |

**Recommended combination: A + D** (4-6 weeks). This gives the project:
- A **semantic model auto-generator** that applies graph algorithms, decision tree classification, and association rule mining to produce the Power BI data model -- a tangible, useful artefact (LO1, LO2, LO3)
- **Quantitative evaluation** with BLEU scores, ablation studies, and statistical significance -- measurable, reproducible findings (LO3, LO5)
- **Visual outputs**: ER diagrams, box plots, confusion matrices (LO4)
- A defensible answer to "where is the data science?" -- graph-based metadata mining + systematic evaluation with ML classifiers

**Extended combination: A + B + D + E** (7-9 weeks) would additionally add unsupervised clustering, data lineage DAGs, and centrality analysis -- making the data science component the strongest part of the thesis.

---

## 9. Summary of Techniques by Step

| Step | Technique | Model/Algorithm | Purpose |
|------|-----------|-----------------|---------|
| 1 | Template matching | pyautogui (OpenCV) | Resolution-independent UI element detection |
| 2 | Recursive flattening | Custom DFS | XML hierarchy to tabular structure |
| 3 | Lookup table | Pandas merge | QlikView to Power BI type mapping |
| 4 | RAG + LLM | text-embedding-3-small + GPT-4o | QVS script to M Query translation |
| 5 | LLM + type inference | GPT-4o + heuristic mapping | Expression to DAX measure translation |
| 6 | Data integration | Pandas multi-join | Multi-source synthesis to enriched JSON |
| 7 | Feature engineering + multi-criteria scoring | Min-max normalisation + weighted aggregation | Migration complexity analysis and effort estimation |
