# Translation Quality Evaluation Framework

## 1. Overview

This document describes Step 9 of the VizShifter pipeline: a quantitative evaluation framework that measures the accuracy of LLM-generated DAX measures and M Query scripts against human-validated gold-standard references.

The framework addresses a critical gap identified in the self-assessment (Section 5 of `pipeline.md`): the project previously consumed AI outputs without measuring their quality. This step transforms anecdotal observations ("the pipeline ran successfully") into measurable, reproducible findings ("mean BLEU-4 = 0.84, with 100% functional correctness on table/column references").

**Implementation files:**
- `src/utils/evaluation.py` -- evaluation engine (metrics, loading, classification)
- `assets/evaluation/gold_standard.json` -- 16 human-validated reference translations
- `src/app.py` -- Streamlit "Translation Quality" page (interactive results viewer)

---

## 2. Gold-Standard Dataset

### 2.1 Construction

16 reference translations were manually created and validated:

| Type | Count | Source | Validation |
|------|-------|--------|------------|
| DAX measures | 8 | `expressions.csv` (CH01, CH02) | Verified against `fields.csv` for correct table/column resolution |
| M Query tables | 8 | `script.qvs` (4 tabs) | Verified for structural equivalence to QlikView LOAD statements |

Each gold-standard entry includes:
- The original QlikView expression or script
- The human-validated reference translation
- Validation notes explaining the rationale

### 2.2 DAX Gold Standard (8 entries)

| ID | ObjectId | QlikView Expression | Reference DAX | Notes |
|----|----------|-------------------|---------------|-------|
| dax_001 | CH01 | `Sum ([# Departures Performed])` | `'# of Flights' = SUM('Main Data'[# Departures Performed])` | Measure name from parent label |
| dax_002 | CH01 | `Sum ([# Transported Passengers])` | `'# of Enplanned Passengers' = SUM('Main Data'[# Transported Passengers])` | Field resolved via fields.csv |
| dax_003 | CH01 | `Sum ([# Transported Freight])` | `'Transported Freight' = SUM('Main Data'[# Transported Freight])` | Parent label, no "Total" prefix |
| dax_004 | CH01 | `Sum ([# Transported Mail])` | `'Transported Mail' = SUM('Main Data'[# Transported Mail])` | Same pattern as dax_003 |
| dax_005 | CH02 | `Sum ([# Departures Performed])` | `'Flights' = SUM('Main Data'[# Departures Performed])` | Parent label "Flights" |
| dax_006 | CH02 | `Sum ([# Transported Passengers])` | `'Passengers' = SUM('Main Data'[# Transported Passengers])` | Parent label "Passengers" |
| dax_007 | CH02 | `Sum ([# Transported Freight])` | `'Freight' = SUM('Main Data'[# Transported Freight])` | Parent label "Freight" |
| dax_008 | CH02 | `Sum ([# Transported Mail])` | `'Mail' = SUM('Main Data'[# Transported Mail])` | Parent label "Mail" |

**Design rationale:** The gold standard uses the QlikView expression parent label as the measure name (e.g., "Flights" not "Total Departures Performed"), following the convention that Power BI measure names should match the original report's visual labels for traceability.

### 2.3 M Query Gold Standard (8 entries)

| ID | Table | QlikView Source | Key Differences vs Generated |
|----|-------|----------------|------------------------------|
| mq_001 | MainData | LOAD 51 fields FROM Flight Data.qvd | Step name `TypedColumns` vs `ChangedType`; uses `type text` vs `Text.Type` |
| mq_002 | CarrierGroups | LOAD 2 fields FROM Carrier Groups.qvd | Step name `PromotedHeaders` vs `CarrierGroups` |
| mq_003 | Airlines | LOAD 2 fields FROM Airlines.qvd | Step name difference |
| mq_004 | CarrierOperatingRegion | LOAD 2 fields FROM Carrier Operating Region.qvd | Step name difference |
| mq_005 | FlightTypes | LOAD 2 fields FROM Flight Types.qvd | Step name difference |
| mq_006 | AircraftGroups | LOAD 2 fields + rename FROM Aircraft Groups.qvd | Removes no-op rename (`"Aircraft Group"` -> `"Aircraft Group"`) |
| mq_007 | AircraftTypes | LOAD 2 fields + rename FROM Aircraft Types.qvd | Removes no-op rename |
| mq_008 | DistanceGroups | LOAD 2 fields + rename FROM Distance Groups.qvd | Removes spurious `Source{[Name="Table"]}[Content]` step and no-op rename |

---

## 3. Evaluation Metrics

### 3.1 Code Tokenisation

All text-based metrics operate on tokenised code. The tokeniser (`tokenize_code()`) uses a regex that preserves:
- Single-quoted identifiers: `'Main Data'`
- Double-quoted strings: `"path"`
- Bracket-quoted identifiers: `[# Departures Performed]`
- Word tokens: function names, keywords
- Single punctuation/operators: `=`, `(`, `)`, `,`

### 3.2 BLEU-4 (Papineni et al., 2002)

Standard machine translation metric adapted for code:

1. Compute n-gram precision for n = 1, 2, 3, 4 between reference and candidate token sequences
2. Apply clipped counting: each candidate n-gram credited at most as many times as it appears in the reference
3. Brevity penalty: BP = exp(1 - |ref| / |cand|) if |cand| < |ref|, else 1.0
4. BLEU-4 = BP x exp( (log p1 + log p2 + log p3 + log p4) / 4 )

**Interpretation:** 1.0 = identical token sequences; 0.0 = no n-gram overlap. Scores above 0.7 indicate high similarity for code translation.

### 3.3 Token-Level Precision / Recall / F1

Treats reference and candidate as multi-sets (bags) of tokens:

- **Precision** = |intersection| / |candidate| -- what fraction of generated tokens are correct
- **Recall** = |intersection| / |reference| -- what fraction of expected tokens appear
- **F1** = 2 x precision x recall / (precision + recall)

Captures whether the correct identifiers, DAX functions, table names, and column references are present, regardless of order.

### 3.4 Normalised Edit Similarity (Levenshtein)

1. Tokenise both strings and join with spaces
2. Compute Levenshtein edit distance (insertions, deletions, substitutions)
3. Normalise: similarity = 1 - (distance / max_length)

Complements token-level metrics by penalising ordering differences and extra/missing content.

### 3.5 Structural Similarity

Domain-specific decomposition that evaluates semantic correctness beyond textual overlap.

**DAX structural analysis:**
- Extracts three components via regex: measure name, DAX functions (SUM, CALCULATE, etc.), table[column] references
- Per-component scoring:
  - Name match: binary (1 if identical after normalisation, 0 otherwise)
  - Function match: Jaccard similarity on function sets
  - Reference match: Jaccard similarity on (table, column) pairs
- Weighted combination: **20% name + 40% functions + 40% references**
- Rationale: correct function and column references matter more than the label

**M Query structural analysis:**
- Extracts: data source calls, table operations (Table.PromoteHeaders, etc.), column definitions
- Jaccard similarity per component: **30% sources + 30% operations + 40% columns**

### 3.6 Quality Classification

Composite score combining all metrics:

```
Composite = 0.3 x BLEU-4 + 0.3 x Token F1 + 0.4 x Structural Similarity
```

| Composite | Tier | Interpretation |
|-----------|------|----------------|
| = 1.0 (normalised) | Exact Match | Identical after whitespace normalisation |
| >= 0.85 | High Quality | Functionally correct, minor cosmetic differences |
| >= 0.65 | Acceptable | Correct logic, notable naming or structural differences |
| >= 0.40 | Needs Review | Partial correctness, manual validation required |
| < 0.40 | Poor | Significant errors, likely incorrect translation |

---

## 4. Results

### 4.1 Aggregate Metrics (Airline Operations, N=16)

| Metric | Mean | Std | Min | Max |
|--------|------|-----|-----|-----|
| BLEU-4 | 0.840 | 0.079 | 0.650 | 1.000 |
| Token F1 | 0.902 | 0.065 | 0.769 | 1.000 |
| Edit Similarity | 0.849 | 0.090 | 0.661 | 1.000 |
| Structural Similarity | 0.902 | 0.063 | 0.800 | 1.000 |

### 4.2 Quality Distribution

| Tier | Count | Percentage |
|------|-------|------------|
| Exact Match | 2 | 12.5% |
| High Quality | 7 | 43.8% |
| Acceptable | 7 | 43.8% |
| Needs Review | 0 | 0.0% |
| Poor | 0 | 0.0% |

### 4.3 Per-Translation Results -- DAX

| ID | BLEU-4 | Token F1 | Structural | Quality |
|----|--------|----------|------------|---------|
| dax_001 | 1.000 | 1.000 | 1.000 | Exact Match |
| dax_002 | 1.000 | 1.000 | 1.000 | Exact Match |
| dax_003 | 0.809 | 0.900 | 0.800 | Acceptable |
| dax_004 | 0.809 | 0.900 | 0.800 | Acceptable |
| dax_005 | 0.809 | 0.818 | 0.800 | Acceptable |
| dax_006 | 0.809 | 0.818 | 0.800 | Acceptable |
| dax_007 | 0.809 | 0.818 | 0.800 | Acceptable |
| dax_008 | 0.809 | 0.818 | 0.800 | Acceptable |

**Analysis:** dax_001 and dax_002 are exact matches -- the LLM used the parent label ("# of Flights", "# of Enplanned Passengers") as the measure name. For dax_003-008, the LLM generated more descriptive names (e.g., "Total Transported Freight" instead of "Transported Freight"), producing consistent BLEU scores of 0.81. In all 8 cases, the DAX function (SUM) and table[column] reference ('Main Data'[field]) are correct -- 100% function match, 100% reference match.

### 4.4 Per-Translation Results -- M Query

| ID | Table | BLEU-4 | Token F1 | Structural | Quality |
|----|-------|--------|----------|------------|---------|
| mq_001 | MainData | 0.772 | 0.975 | 0.964 | High Quality |
| mq_002 | CarrierGroups | 0.859 | 0.857 | 1.000 | High Quality |
| mq_003 | Airlines | 0.859 | 0.857 | 1.000 | High Quality |
| mq_004 | CarrierOperatingRegion | 0.859 | 0.857 | 1.000 | High Quality |
| mq_005 | FlightTypes | 0.859 | 0.857 | 1.000 | High Quality |
| mq_006 | AircraftGroups | 0.860 | 0.889 | 0.870 | High Quality |
| mq_007 | AircraftTypes | 0.860 | 0.889 | 0.870 | High Quality |
| mq_008 | DistanceGroups | 0.650 | 0.769 | 0.813 | Acceptable |

**Analysis:**
- **MainData (mq_001):** High quality despite a lower BLEU (0.77) because the structural similarity is very high (0.96). The BLEU penalty comes from step name differences (`ChangedType` vs `TypedColumns`) and type notation (`Text.Type` vs `type text`), which are cosmetic -- both are valid M Query.
- **Simple tables (mq_002-005):** Consistent BLEU of 0.86 with perfect structural match (1.0). The only difference is step naming (`CarrierGroups` vs `PromotedHeaders`).
- **Renamed tables (mq_006-007):** Slightly lower structural match (0.87) because the generated versions include no-op rename operations (renaming a column to itself).
- **DistanceGroups (mq_008):** Lowest scores (BLEU 0.65) due to a spurious intermediate step `Source{[Name="Table"]}[Content]` in the generated output that is unnecessary for QVD loading.

---

## 5. Key Findings

1. **Functional correctness is high:** All 16 translations produce valid DAX/M Query with correct functions and table/column references. Zero translations classified as "Needs Review" or "Poor".

2. **Score variation is driven by naming, not logic:** The primary source of BLEU reduction is measure naming differences (LLM generates descriptive names vs. gold standard using parent labels). This is stylistic, not functional.

3. **Structural analysis outperforms BLEU for code evaluation:** BLEU penalises valid variations (e.g., `Text.Type` vs `type text`, different step names). The structural similarity metric correctly identifies these as equivalent, producing scores of 0.80-1.00 even where BLEU drops to 0.65-0.81.

4. **Edge cases identified:** The DistanceGroups table (mq_008) reveals a concrete LLM error -- an unnecessary intermediate navigation step. This was only detectable through systematic evaluation, not manual inspection.

5. **Defensible thesis statement:** "The RAG-augmented GPT-4o pipeline achieves a mean BLEU-4 of 0.84 and structural similarity of 0.90 across 16 translations, with 100% functional correctness on DAX function and table/column references."

---

## 6. Streamlit Integration

The evaluation results are displayed interactively in the "Translation Quality" page of the Streamlit app:

- **Summary metrics:** 4 metric cards (BLEU, Token F1, Edit Similarity, Structural Match)
- **Quality distribution:** bar chart of quality tiers
- **Metric summary table:** mean, std, min, max for all 4 metrics
- **Per-translation detail:** expandable panels for each DAX expression and M Query table, showing reference vs generated code, individual metrics, and structural decomposition

Access via sidebar: Navigation > Translation Quality.

---

## 7. Potential Extensions

- **Ablation studies:** Re-run Steps 4-5 with zero-shot (no RAG) and few-shot (fixed examples) configurations. Compare BLEU distributions using Wilcoxon signed-rank test. This would quantify the contribution of RAG to translation quality.
- **Expanded gold standard:** Add complex expressions (SET analysis, AGGR, nested IF) and multi-JOIN scripts to test the framework on harder translations.
- **CodeBLEU:** Add syntax-tree-based matching for DAX (weighted sum of n-gram, syntax, dataflow, and semantic match).
