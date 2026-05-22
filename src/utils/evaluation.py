"""Translation Quality Evaluation Framework.

Computes BLEU, token-level precision/recall/F1, normalised edit similarity,
and structural similarity for LLM-generated DAX and M Query translations
evaluated against human-validated gold-standard references.
"""

import json
import math
import re
import numpy as np
import pandas as pd
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Code tokenisation
# ---------------------------------------------------------------------------

_CODE_TOKEN_RE = re.compile(
    r"""
    '[^']*'           # single-quoted string
    | "[^"]*"         # double-quoted string
    | \[[^\]]*\]      # bracket-quoted identifier
    | \w+             # word token
    | [^\s\w]         # single punctuation / operator
    """,
    re.VERBOSE,
)


def tokenize_code(code: str) -> List[str]:
    return [t.strip() for t in _CODE_TOKEN_RE.findall(code.strip()) if t.strip()]


# ---------------------------------------------------------------------------
# BLEU score (sentence-level, up to 4-gram)
# ---------------------------------------------------------------------------

def _count_ngrams(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _clipped_count(ref_tokens: List[str], cand_tokens: List[str], n: int) -> Tuple[int, int]:
    ref_ng = _count_ngrams(ref_tokens, n)
    cand_ng = _count_ngrams(cand_tokens, n)
    clipped = sum(min(c, ref_ng[ng]) for ng, c in cand_ng.items())
    total = max(sum(cand_ng.values()), 1)
    return clipped, total


def compute_bleu(reference: str, candidate: str, max_n: int = 4) -> Dict[str, float]:
    ref_tok = tokenize_code(reference)
    cand_tok = tokenize_code(candidate)

    zero = {f"bleu_{i}": 0.0 for i in range(1, max_n + 1)}
    zero.update({"brevity_penalty": 0.0, "bleu": 0.0})
    if not cand_tok or not ref_tok:
        return zero

    bp = math.exp(1 - len(ref_tok) / len(cand_tok)) if len(cand_tok) < len(ref_tok) else 1.0

    precisions: List[float] = []
    result: Dict[str, float] = {"brevity_penalty": round(bp, 4)}

    for n in range(1, max_n + 1):
        clipped, total = _clipped_count(ref_tok, cand_tok, n)
        p = clipped / total if total > 0 else 0.0
        result[f"bleu_{n}"] = round(p, 4)
        precisions.append(p)

    log_avg = 0.0
    for p in precisions:
        if p == 0:
            log_avg = float("-inf")
            break
        log_avg += math.log(p)

    result["bleu"] = 0.0 if log_avg == float("-inf") else round(bp * math.exp(log_avg / max_n), 4)
    return result


# ---------------------------------------------------------------------------
# Token-level precision / recall / F1
# ---------------------------------------------------------------------------

def compute_token_metrics(reference: str, candidate: str) -> Dict[str, float]:
    ref_c = Counter(tokenize_code(reference))
    cand_c = Counter(tokenize_code(candidate))

    if not ref_c or not cand_c:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    common = sum((ref_c & cand_c).values())
    precision = common / sum(cand_c.values())
    recall = common / sum(ref_c.values())
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


# ---------------------------------------------------------------------------
# Normalised edit similarity (Levenshtein on tokenised strings)
# ---------------------------------------------------------------------------

def _levenshtein(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + (0 if c1 == c2 else 1)))
        prev = curr
    return prev[-1]


def compute_edit_similarity(reference: str, candidate: str) -> float:
    ref_norm = " ".join(tokenize_code(reference))
    cand_norm = " ".join(tokenize_code(candidate))
    max_len = max(len(ref_norm), len(cand_norm))
    if max_len == 0:
        return 1.0
    return round(1.0 - _levenshtein(ref_norm, cand_norm) / max_len, 4)


# ---------------------------------------------------------------------------
# Exact match (after normalisation)
# ---------------------------------------------------------------------------

def _normalise(code: str) -> str:
    return re.sub(r"\s+", " ", code.strip().lower())


def compute_exact_match(reference: str, candidate: str) -> bool:
    return _normalise(reference) == _normalise(candidate)


# ---------------------------------------------------------------------------
# Structural similarity — DAX
# ---------------------------------------------------------------------------

_DAX_MEASURE_RE = re.compile(r"'([^']+)'\s*=\s*(.+)", re.DOTALL)
_DAX_FUNC_RE = re.compile(
    r"\b(SUM|AVERAGE|COUNT|COUNTROWS|DISTINCTCOUNT|MIN|MAX|CALCULATE|DIVIDE|IF|SWITCH|SUMX|AVERAGEX|FILTER|ALL|VALUES|RELATED|BLANK)\s*\(",
    re.IGNORECASE,
)
_DAX_REF_RE = re.compile(r"'([^']+)'\[([^\]]+)\]")


def _extract_dax_components(dax: str) -> Dict:
    m = _DAX_MEASURE_RE.search(dax)
    name = m.group(1).strip() if m else ""
    body = m.group(2).strip() if m else dax
    funcs = sorted(set(f.upper() for f in _DAX_FUNC_RE.findall(body)))
    refs = sorted(set((t.strip(), c.strip()) for t, c in _DAX_REF_RE.findall(body)))
    return {"measure_name": name, "functions": funcs, "references": refs}


def compute_dax_structural_similarity(reference: str, candidate: str) -> Dict[str, float]:
    rc = _extract_dax_components(reference)
    cc = _extract_dax_components(candidate)

    name_match = 1.0 if _normalise(rc["measure_name"]) == _normalise(cc["measure_name"]) else 0.0

    def _jaccard(a, b):
        sa, sb = set(a), set(b)
        u = sa | sb
        return len(sa & sb) / len(u) if u else 1.0

    func_match = _jaccard(rc["functions"], cc["functions"])
    ref_match = _jaccard(rc["references"], cc["references"])
    overall = name_match * 0.2 + func_match * 0.4 + ref_match * 0.4

    return {
        "name_match": round(name_match, 4),
        "function_match": round(func_match, 4),
        "reference_match": round(ref_match, 4),
        "structural_similarity": round(overall, 4),
    }


# ---------------------------------------------------------------------------
# Structural similarity — M Query
# ---------------------------------------------------------------------------

_MQ_SOURCE_RE = re.compile(
    r"(?:Qvd\.Document|Csv\.Document|Excel\.Workbook|Sql\.Database|File\.Contents)\s*\([^)]*\)",
    re.IGNORECASE,
)
_MQ_STEP_RE = re.compile(
    r"(Table\.(?:PromoteHeaders|TransformColumnTypes|RenameColumns|SelectRows|Join|Combine|AddColumn|RemoveColumns|ExpandTableColumn))",
    re.IGNORECASE,
)
_MQ_COL_RE = re.compile(r'"([^"]{2,})"')


def _extract_m_query_components(mq: str) -> Dict:
    sources = sorted(set(s.strip().lower() for s in _MQ_SOURCE_RE.findall(mq)))
    ops = sorted(set(o.strip() for o in _MQ_STEP_RE.findall(mq)))
    cols = sorted(set(_MQ_COL_RE.findall(mq)))
    return {"sources": sources, "operations": ops, "columns": cols}


def compute_m_query_structural_similarity(reference: str, candidate: str) -> Dict[str, float]:
    rc = _extract_m_query_components(reference)
    cc = _extract_m_query_components(candidate)

    def _jaccard(a: list, b: list) -> float:
        sa = set(str(x).lower() for x in a)
        sb = set(str(x).lower() for x in b)
        u = sa | sb
        return len(sa & sb) / len(u) if u else 1.0

    src = _jaccard(rc["sources"], cc["sources"])
    ops = _jaccard(rc["operations"], cc["operations"])
    cols = _jaccard(rc["columns"], cc["columns"])
    overall = src * 0.3 + ops * 0.3 + cols * 0.4

    return {
        "source_match": round(src, 4),
        "operation_match": round(ops, 4),
        "column_match": round(cols, 4),
        "structural_similarity": round(overall, 4),
    }


# ---------------------------------------------------------------------------
# Single-pair evaluation
# ---------------------------------------------------------------------------

def evaluate_single(reference: str, candidate: str, translation_type: str = "dax") -> Dict:
    bleu = compute_bleu(reference, candidate)
    tokens = compute_token_metrics(reference, candidate)
    edit_sim = compute_edit_similarity(reference, candidate)
    exact = compute_exact_match(reference, candidate)

    structural = (
        compute_dax_structural_similarity(reference, candidate)
        if translation_type == "dax"
        else compute_m_query_structural_similarity(reference, candidate)
    )

    return {
        "bleu": bleu,
        "token_metrics": tokens,
        "edit_similarity": edit_sim,
        "exact_match": exact,
        "structural": structural,
    }


# ---------------------------------------------------------------------------
# Quality classification
# ---------------------------------------------------------------------------

QUALITY_TIERS = [
    ("Exact Match", "#22c55e"),
    ("High Quality", "#22c55e"),
    ("Acceptable", "#eab308"),
    ("Needs Review", "#f97316"),
    ("Poor", "#ef4444"),
]


def classify_quality(metrics: Dict) -> Tuple[str, str]:
    if metrics.get("exact_match"):
        return QUALITY_TIERS[0]

    bleu = metrics["bleu"]["bleu"]
    f1 = metrics["token_metrics"]["f1"]
    struct = metrics["structural"]["structural_similarity"]
    composite = bleu * 0.3 + f1 * 0.3 + struct * 0.4

    if composite >= 0.85:
        return QUALITY_TIERS[1]
    if composite >= 0.65:
        return QUALITY_TIERS[2]
    if composite >= 0.40:
        return QUALITY_TIERS[3]
    return QUALITY_TIERS[4]


# ---------------------------------------------------------------------------
# Load gold standard & generated outputs
# ---------------------------------------------------------------------------

def load_gold_standard(project_root: Path) -> Optional[Dict]:
    path = project_root / "assets" / "evaluation" / "gold_standard.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_generated_dax(report_folder: Path) -> Dict[str, str]:
    path = report_folder / "expressions_with_dax.csv"
    if not path.exists():
        return {}
    df = None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None:
        return {}
    df.columns = df.columns.str.strip()
    result = {}
    for _, row in df.iterrows():
        oid = str(row.get("ObjectId", "")).strip().strip('"')
        parent = str(row.get("Parent", "")).strip().strip('"')
        dax = str(row.get("DAX", "")).strip().strip('"')
        if oid and dax:
            result[f"{oid}|{parent}"] = dax
    return result


def _load_generated_m_query(report_folder: Path) -> Dict[str, str]:
    path = report_folder / "m_query_output.csv"
    if not path.exists():
        return {}
    df = None
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if df is None:
        return {}
    df.columns = df.columns.str.strip()
    result = {}
    for _, row in df.iterrows():
        name = str(row.get("TableName", "")).strip()
        script = str(row.get("MQueryScript", "")).strip()
        if name and script:
            result[name] = script
    return result


# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------

def run_evaluation(report_folder: Path, project_root: Path) -> Optional[Dict]:
    gold = load_gold_standard(project_root)
    if gold is None:
        return None

    report_name = report_folder.name
    report_gold = None
    for entry in gold.get("reports", []):
        if entry["report_name"] == report_name:
            report_gold = entry
            break
    if report_gold is None:
        return None

    gen_dax = _load_generated_dax(report_folder)
    gen_mq = _load_generated_m_query(report_folder)

    dax_results: List[Dict] = []
    for gs in report_gold.get("dax", []):
        key = f"{gs['object_id']}|{gs['parent']}"
        gen = gen_dax.get(key, "")
        if not gen:
            for k, v in gen_dax.items():
                if k.startswith(gs["object_id"] + "|") and gs["parent"] in k:
                    gen = v
                    break
        if gen:
            metrics = evaluate_single(gs["reference_dax"], gen, "dax")
            quality, color = classify_quality(metrics)
            dax_results.append({
                "id": gs["id"],
                "object_id": gs["object_id"],
                "qlikview_expression": gs["qlikview_expression"],
                "reference": gs["reference_dax"],
                "generated": gen,
                "metrics": metrics,
                "quality": quality,
                "quality_color": color,
            })

    mq_results: List[Dict] = []
    for gs in report_gold.get("m_query", []):
        gen = gen_mq.get(gs["table_name"], "")
        if gen:
            metrics = evaluate_single(gs["reference_m_query"], gen, "m_query")
            quality, color = classify_quality(metrics)
            mq_results.append({
                "id": gs["id"],
                "table_name": gs["table_name"],
                "reference": gs["reference_m_query"],
                "generated": gen,
                "metrics": metrics,
                "quality": quality,
                "quality_color": color,
            })

    all_res = dax_results + mq_results
    if not all_res:
        return None

    bleu_scores = [r["metrics"]["bleu"]["bleu"] for r in all_res]
    f1_scores = [r["metrics"]["token_metrics"]["f1"] for r in all_res]
    edit_sims = [r["metrics"]["edit_similarity"] for r in all_res]
    struct_sims = [r["metrics"]["structural"]["structural_similarity"] for r in all_res]
    exact_n = sum(1 for r in all_res if r["metrics"]["exact_match"])

    def _stats(arr):
        return {
            "mean": round(float(np.mean(arr)), 4),
            "std": round(float(np.std(arr)), 4),
            "min": round(float(np.min(arr)), 4),
            "max": round(float(np.max(arr)), 4),
        }

    summary = {
        "total_translations": len(all_res),
        "dax_count": len(dax_results),
        "m_query_count": len(mq_results),
        "exact_matches": exact_n,
        "exact_match_rate": round(exact_n / len(all_res), 4),
        "bleu": _stats(bleu_scores),
        "token_f1": _stats(f1_scores),
        "edit_similarity": _stats(edit_sims),
        "structural_similarity": _stats(struct_sims),
        "quality_distribution": {
            tier: sum(1 for r in all_res if r["quality"] == tier)
            for tier, _ in QUALITY_TIERS
        },
    }

    return {
        "report_name": report_name,
        "summary": summary,
        "dax_results": dax_results,
        "m_query_results": mq_results,
    }
