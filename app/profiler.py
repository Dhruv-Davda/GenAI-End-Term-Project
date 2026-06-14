"""Automatic data profiling: schema, types, null rates, distributions, anomalies."""
import math
import re

import numpy as np
import pandas as pd

_DATE_NAME = re.compile(r"date|time|day|month|year|timestamp", re.I)


def _native(v):
    """Convert numpy/pandas scalars to JSON-safe Python values."""
    if v is None:
        return None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        f = float(v)
        return None if math.isnan(f) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, np.ndarray):
        return [_native(x) for x in v.tolist()]
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def _round(v, n=3):
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return round(f, n)
    except (TypeError, ValueError):
        return None


def _semantic(name, s):
    n = len(s)
    nun = int(s.nunique(dropna=True))
    if pd.api.types.is_bool_dtype(s):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    if pd.api.types.is_numeric_dtype(s):
        if nun == n and n > 5 and _DATE_NAME.search(str(name)) is None:
            # e.g. an integer primary key
            if "id" in str(name).lower():
                return "identifier"
        return "numeric"
    # object / category / string
    if nun == n and n > 5:
        return "identifier"
    if n and nun > 50 and nun / n > 0.6:
        return "text"
    return "categorical"


def _column(name, s, n_rows):
    nulls = int(s.isna().sum())
    null_pct = round(100 * nulls / n_rows, 1) if n_rows else 0.0
    unique = int(s.nunique(dropna=True))
    semantic = _semantic(name, s)
    stats = {}

    try:
        if semantic == "numeric":
            num = pd.to_numeric(s, errors="coerce").dropna()
            if len(num):
                q1, q3 = num.quantile(0.25), num.quantile(0.75)
                iqr = q3 - q1
                lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outliers = int(((num < lo) | (num > hi)).sum())
                stats = {
                    "min": _round(num.min()),
                    "max": _round(num.max()),
                    "mean": _round(num.mean()),
                    "median": _round(num.median()),
                    "std": _round(num.std()),
                    "outliers": outliers,
                }
        elif semantic == "datetime":
            dt = pd.to_datetime(s, errors="coerce").dropna()
            if len(dt):
                stats = {
                    "min": dt.min().isoformat(),
                    "max": dt.max().isoformat(),
                    "span_days": int((dt.max() - dt.min()).days),
                }
        elif semantic in ("categorical", "boolean", "text"):
            vc = s.value_counts(dropna=True).head(5)
            stats = {"top": [[_native(k), int(v)] for k, v in vc.items()]}
    except Exception:
        stats = {}

    # A few example values for the UI.
    sample = [_native(v) for v in s.dropna().unique()[:3]]

    note = ""
    if semantic == "categorical" and _DATE_NAME.search(str(name)):
        note = "name suggests dates — consider pd.to_datetime"

    return {
        "name": str(name),
        "dtype": str(s.dtype),
        "semantic": semantic,
        "nulls": nulls,
        "null_pct": null_pct,
        "unique": unique,
        "sample": sample,
        "stats": stats,
        "note": note,
    }


def profile(df, tables=None, main_key=None):
    n_rows = int(len(df))
    n_cols = int(df.shape[1])

    columns = [_column(name, df[name], n_rows) for name in df.columns]

    total_cells = n_rows * n_cols
    missing_cells = int(df.isna().sum().sum())
    missing_pct = round(100 * missing_cells / total_cells, 1) if total_cells else 0.0

    try:
        duplicates = int(df.duplicated().sum())
    except Exception:
        duplicates = 0

    try:
        memory_mb = round(df.memory_usage(deep=True).sum() / 1e6, 2)
    except Exception:
        memory_mb = None

    type_counts = {}
    for c in columns:
        type_counts[c["semantic"]] = type_counts.get(c["semantic"], 0) + 1

    anomalies = []
    for c in columns:
        if c["null_pct"] >= 30:
            anomalies.append(
                f"'{c['name']}' is {c['null_pct']}% missing — treat its results with caution."
            )
        if c["unique"] <= 1 and n_rows > 1:
            anomalies.append(f"'{c['name']}' is constant (a single value).")
        out = (c.get("stats") or {}).get("outliers", 0)
        if out and out > 0:
            anomalies.append(
                f"'{c['name']}' has {out} potential outlier(s) (IQR method)."
            )
    if duplicates > 0:
        anomalies.append(f"{duplicates} duplicate row(s) detected.")
    anomalies = anomalies[:12]

    # Sample rows for the preview table (cap width to keep payload small).
    head_cols = list(df.columns)[:12]
    head = []
    for _, row in df.head(6).iterrows():
        head.append({str(k): _native(row[k]) for k in head_cols})

    tables_info = []
    if tables:
        for name, t in tables.items():
            tables_info.append(
                {"name": str(name), "rows": int(len(t)), "cols": int(t.shape[1])}
            )

    return {
        "shape": {"rows": n_rows, "cols": n_cols},
        "memory_mb": memory_mb,
        "missing_pct": missing_pct,
        "missing_cells": missing_cells,
        "duplicates": duplicates,
        "type_counts": type_counts,
        "columns": columns,
        "anomalies": anomalies,
        "head": head,
        "head_cols": [str(c) for c in head_cols],
        "tables_info": tables_info,
        "main_key": str(main_key) if main_key else None,
    }
