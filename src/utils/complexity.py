"""Migration Complexity Analysis — feature extraction and weighted scoring.

Extracts quantitative features from QlikView metadata across four dimensions
(Data Model, Expressions, Script, Layout), normalises each to [0, 1] using
predefined reference ranges, and produces a composite score on a 0-100 scale.
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CATEGORY_WEIGHTS = {
    "Data Model": 0.30,
    "Expressions": 0.25,
    "Script": 0.25,
    "Layout": 0.20,
}

FEATURE_RANGES: Dict[str, Tuple[float, float]] = {
    # Data Model
    "field_count":          (5, 200),
    "key_field_count":      (0, 20),
    "measure_field_count":  (0, 30),
    "avg_cardinality":      (10, 100_000),
    "multi_table_fields":   (0, 15),
    "type_diversity":       (1, 6),
    # Expressions
    "expression_count":     (1, 50),
    "avg_expression_length": (10, 200),
    "has_set_analysis":     (0, 1),
    "nested_function_depth": (1, 5),
    "aggregation_diversity": (1, 8),
    "dax_translation_gap":  (0, 1),
    # Script
    "line_count":           (10, 1000),
    "load_statement_count": (1, 30),
    "join_count":           (0, 10),
    "resident_count":       (0, 10),
    "variable_count":       (0, 30),
    "has_subroutines":      (0, 1),
    "has_loops":            (0, 1),
    "tab_count":            (1, 15),
    # Layout
    "object_count":         (1, 100),
    "sheet_count":          (1, 20),
    "max_objects_per_sheet": (1, 30),
    "unique_object_types":  (1, 10),
    "chart_count":          (0, 20),
    "dimension_count":      (0, 50),
    "avg_dims_per_object":  (0, 5),
}

FEATURE_WEIGHTS = {
    "data_model": {
        "field_count": 0.20, "key_field_count": 0.15, "measure_field_count": 0.15,
        "avg_cardinality": 0.20, "multi_table_fields": 0.20, "type_diversity": 0.10,
    },
    "expressions": {
        "expression_count": 0.20, "avg_expression_length": 0.15, "has_set_analysis": 0.20,
        "nested_function_depth": 0.20, "aggregation_diversity": 0.10, "dax_translation_gap": 0.15,
    },
    "script": {
        "line_count": 0.15, "load_statement_count": 0.15, "join_count": 0.20,
        "resident_count": 0.10, "variable_count": 0.10, "has_subroutines": 0.10,
        "has_loops": 0.10, "tab_count": 0.10,
    },
    "layout": {
        "object_count": 0.20, "sheet_count": 0.15, "max_objects_per_sheet": 0.15,
        "unique_object_types": 0.15, "chart_count": 0.15, "dimension_count": 0.10,
        "avg_dims_per_object": 0.10,
    },
}

CLASSIFICATION: List[Tuple[float, str, str]] = [
    (25,  "Low",      "Straightforward migration with minimal manual intervention."),
    (50,  "Medium",   "Moderate complexity; some expressions or joins need review."),
    (75,  "High",     "Significant complexity; dedicated migration sprint recommended."),
    (100, "Critical", "Very high complexity; phased migration with extensive testing required."),
]

EFFORT_DAYS = {"Low": (1, 3), "Medium": (3, 7), "High": (7, 15), "Critical": (15, 30)}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_csv(folder: Path, filename: str) -> Optional[pd.DataFrame]:
    path = folder / filename
    if not path.exists():
        return None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            for col in df.select_dtypes(include="object").columns:
                df[col] = df[col].astype(str).str.strip()
            return df
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _read_script(folder: Path) -> str:
    path = folder / "script.qvs"
    if not path.exists():
        return ""
    for enc in ("utf-16", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def _normalize(value: float, min_val: float, max_val: float) -> float:
    if max_val <= min_val:
        return 0.0
    return float(np.clip((value - min_val) / (max_val - min_val), 0.0, 1.0))

# ---------------------------------------------------------------------------
# Feature extraction — one function per dimension
# ---------------------------------------------------------------------------

def extract_data_model_features(folder: Path) -> Dict[str, float]:
    df = _read_csv(folder, "fields.csv")
    if df is None or df.empty:
        return {k: 0.0 for k in FEATURE_WEIGHTS["data_model"]}

    tags_col = df["FieldTags"] if "FieldTags" in df.columns else pd.Series(dtype=str)
    table_count_col = pd.to_numeric(df.get("FieldTableCount", pd.Series(dtype=float)), errors="coerce").fillna(0)
    value_count_col = pd.to_numeric(df.get("FieldValueCount", pd.Series(dtype=float)), errors="coerce").fillna(0)

    key_mask = tags_col.str.contains(r"\$key", case=False, na=False)
    numeric_mask = tags_col.str.contains(r"\$numeric", case=False, na=False)

    all_tags = set()
    for t in tags_col.dropna():
        all_tags.update(tok.strip().lower() for tok in str(t).split(";") if tok.strip().startswith("$"))

    return {
        "field_count": float(len(df)),
        "key_field_count": float(key_mask.sum()),
        "measure_field_count": float((numeric_mask & ~key_mask).sum()),
        "avg_cardinality": float(value_count_col.mean()) if len(value_count_col) else 0.0,
        "multi_table_fields": float((table_count_col > 1).sum()),
        "type_diversity": float(len(all_tags)) if all_tags else 1.0,
    }


def extract_expression_features(folder: Path) -> Dict[str, float]:
    df = _read_csv(folder, "expressions.csv")
    dax_df = _read_csv(folder, "expressions_with_dax.csv")

    if df is None or df.empty:
        return {k: 0.0 for k in FEATURE_WEIGHTS["expressions"]}

    expr_col = df["Expression"] if "Expression" in df.columns else pd.Series(dtype=str)
    expr_texts = expr_col.dropna().astype(str)

    agg_pattern = re.compile(
        r"(?i)\b(Sum|Count|Avg|Min|Max|Rank|FirstSortedValue|Concat|NullCount|MissingCount|Only|Mode)\s*\("
    )
    agg_funcs = set()
    max_depth = 1
    has_set = 0
    for text in expr_texts:
        agg_funcs.update(m.group(1).lower() for m in agg_pattern.finditer(text))
        depth = text.count("(")
        if depth > max_depth:
            max_depth = depth
        if re.search(r"\{<", text):
            has_set = 1

    dax_gap = 0.0
    if dax_df is not None and "DAX" in dax_df.columns:
        total = len(dax_df)
        translated = dax_df["DAX"].dropna().astype(str).str.strip().replace("", np.nan).dropna()
        dax_gap = 1.0 - (len(translated) / total) if total > 0 else 0.0

    return {
        "expression_count": float(len(df)),
        "avg_expression_length": float(expr_texts.str.len().mean()) if len(expr_texts) else 0.0,
        "has_set_analysis": float(has_set),
        "nested_function_depth": float(max_depth),
        "aggregation_diversity": float(len(agg_funcs)) if agg_funcs else 1.0,
        "dax_translation_gap": float(dax_gap),
    }


def extract_script_features(folder: Path) -> Dict[str, float]:
    text = _read_script(folder)
    if not text:
        return {k: 0.0 for k in FEATURE_WEIGHTS["script"]}

    lines = [l for l in text.splitlines() if l.strip()]

    return {
        "line_count": float(len(lines)),
        "load_statement_count": float(len(re.findall(r"(?i)\bLOAD\b", text))),
        "join_count": float(len(re.findall(r"(?i)\bJOIN\b", text))),
        "resident_count": float(len(re.findall(r"(?i)\bRESIDENT\b", text))),
        "variable_count": float(len(re.findall(r"(?i)\b(?:SET|LET)\b", text))),
        "has_subroutines": 1.0 if re.search(r"(?i)\bSUB\b", text) else 0.0,
        "has_loops": 1.0 if re.search(r"(?i)\b(?:FOR|DO\s+WHILE)\b", text) else 0.0,
        "tab_count": float(len(re.findall(r"//\$tab", text, re.IGNORECASE))),
    }


def extract_layout_features(folder: Path) -> Dict[str, float]:
    objects_df = _read_csv(folder, "objects.csv")
    sheets_df = _read_csv(folder, "sheets.csv")
    obj_sheets_df = _read_csv(folder, "objectSheets.csv")
    dims_df = _read_csv(folder, "dimensions.csv")

    obj_count = float(len(objects_df)) if objects_df is not None else 0.0
    sheet_count = float(len(sheets_df)) if sheets_df is not None else 0.0

    max_per_sheet = 0.0
    if obj_sheets_df is not None and "SheetId" in obj_sheets_df.columns:
        counts = obj_sheets_df.groupby("SheetId").size()
        max_per_sheet = float(counts.max()) if len(counts) else 0.0

    unique_types = 0.0
    chart_count = 0.0
    if objects_df is not None and "ObjectType" in objects_df.columns:
        type_col = pd.to_numeric(objects_df["ObjectType"], errors="coerce").dropna()
        unique_types = float(type_col.nunique())
        chart_types = {7, 10, 11, 12, 13}
        chart_count = float(type_col.isin(chart_types).sum())

    dim_count = 0.0
    avg_dims = 0.0
    if dims_df is not None and not dims_df.empty:
        dim_count = float(len(dims_df))
        if "ObjectId" in dims_df.columns:
            avg_dims = float(dims_df.groupby("ObjectId").size().mean())

    return {
        "object_count": obj_count,
        "sheet_count": sheet_count,
        "max_objects_per_sheet": max_per_sheet,
        "unique_object_types": unique_types,
        "chart_count": chart_count,
        "dimension_count": dim_count,
        "avg_dims_per_object": avg_dims,
    }

# ---------------------------------------------------------------------------
# Scoring & classification
# ---------------------------------------------------------------------------

def _generate_recommendations(
    category_scores: Dict[str, float],
    raw_features: Dict[str, Dict[str, float]],
    classification: str,
    effort: Tuple[int, int],
) -> List[str]:
    recs: List[str] = []

    if category_scores.get("Expressions", 0) > 50:
        recs.append(
            "High expression complexity detected — review set analysis patterns "
            "and nested functions for manual DAX validation."
        )
    if category_scores.get("Script", 0) > 50:
        recs.append(
            "Complex load script with JOINs or RESIDENT tables — verify M Query "
            "translations for data model accuracy."
        )
    if category_scores.get("Data Model", 0) > 50:
        recs.append(
            "Large data model with many join keys — consider star schema "
            "optimisation in Power BI."
        )
    if category_scores.get("Layout", 0) > 50:
        recs.append(
            "Dense dashboard layout — plan for multiple Power BI report pages "
            "to maintain usability."
        )

    script = raw_features.get("script", {})
    if script.get("join_count", 0) > 0:
        recs.append(
            f"{int(script['join_count'])} JOIN statement(s) found in QVS — each "
            "requires careful M Query translation."
        )
    if script.get("has_loops", 0):
        recs.append(
            "Script contains loops (FOR/DO WHILE) — these have no direct M Query "
            "equivalent and need manual rewrite."
        )
    if script.get("has_subroutines", 0):
        recs.append(
            "Script contains SUB routines — refactor into Power Query custom functions."
        )

    if not recs:
        recs.append(
            "No major risk factors identified. Standard migration workflow applies."
        )

    recs.append(f"Total estimated effort: {effort[0]}–{effort[1]} person-days ({classification} complexity).")
    return recs


def compute_complexity(folder: Path) -> Optional[Dict]:
    raw = {
        "data_model": extract_data_model_features(folder),
        "expressions": extract_expression_features(folder),
        "script": extract_script_features(folder),
        "layout": extract_layout_features(folder),
    }

    all_zero = all(
        all(v == 0.0 for v in feats.values())
        for feats in raw.values()
    )
    if all_zero:
        return None

    normalized: Dict[str, Dict[str, float]] = {}
    for cat_key, feats in raw.items():
        normalized[cat_key] = {}
        for feat_name, feat_val in feats.items():
            lo, hi = FEATURE_RANGES.get(feat_name, (0, 1))
            normalized[cat_key][feat_name] = _normalize(feat_val, lo, hi)

    cat_key_to_label = {
        "data_model": "Data Model",
        "expressions": "Expressions",
        "script": "Script",
        "layout": "Layout",
    }

    category_scores: Dict[str, float] = {}
    for cat_key, label in cat_key_to_label.items():
        weights = FEATURE_WEIGHTS[cat_key]
        score = sum(
            normalized[cat_key].get(f, 0.0) * w
            for f, w in weights.items()
        )
        category_scores[label] = score * 100

    overall = sum(
        category_scores[label] * CATEGORY_WEIGHTS[label]
        for label in CATEGORY_WEIGHTS
    )

    classification = "Low"
    classification_desc = CLASSIFICATION[0][2]
    for threshold, label, desc in CLASSIFICATION:
        if overall <= threshold:
            classification = label
            classification_desc = desc
            break

    effort = EFFORT_DAYS.get(classification, (1, 3))

    recommendations = _generate_recommendations(category_scores, raw, classification, effort)

    return {
        "overall_score": overall,
        "classification": classification,
        "classification_desc": classification_desc,
        "effort_days": effort,
        "category_scores": category_scores,
        "raw_features": raw,
        "normalized_features": normalized,
        "recommendations": recommendations,
    }
