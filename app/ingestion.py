"""Data ingestion for CSV, TSV, Excel, JSON, and SQLite ("SQL connection").

Returns (main_df, tables, kind, note, main_key) where `tables` maps every
discovered table/sheet to a DataFrame and `main_key` names the primary one.
"""
import io
import json
import os
import sqlite3
import tempfile

import pandas as pd


def load_any(filename, data):
    name = (filename or "data").strip()
    ext = os.path.splitext(name)[1].lower()
    stem = os.path.splitext(os.path.basename(name))[0] or "data"

    if ext in (".csv", ".txt", ""):
        df = pd.read_csv(io.BytesIO(data))
        return df, {stem: df}, "CSV", None, stem

    if ext == ".tsv":
        df = pd.read_csv(io.BytesIO(data), sep="\t")
        return df, {stem: df}, "TSV", None, stem

    if ext in (".xlsx", ".xls"):
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
        tables = {str(k): v for k, v in sheets.items()}
        if not tables:
            raise ValueError("The workbook has no sheets.")
        main = max(tables, key=lambda k: len(tables[k]))
        note = (
            None
            if len(tables) == 1
            else f"Loaded {len(tables)} sheets; primary sheet '{main}'."
        )
        return tables[main], tables, "Excel", note, main

    if ext == ".json":
        df = _read_json(data)
        return df, {stem: df}, "JSON", None, stem

    if ext in (".db", ".sqlite", ".sqlite3"):
        return _read_sqlite(data, ext)

    # Best-effort fallback.
    df = pd.read_csv(io.BytesIO(data))
    return df, {stem: df}, "CSV", None, stem


def _read_json(data):
    try:
        obj = json.loads(data.decode("utf-8"))
    except Exception:
        return pd.read_json(io.BytesIO(data))

    if isinstance(obj, list):
        return pd.json_normalize(obj)
    if isinstance(obj, dict):
        list_keys = [k for k, v in obj.items() if isinstance(v, list)]
        if len(list_keys) == 1:
            return pd.json_normalize(obj[list_keys[0]])
        try:
            return pd.json_normalize(obj)
        except Exception:
            return pd.DataFrame([obj])
    return pd.DataFrame({"value": [obj]})


def _read_sqlite(data, ext):
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
        tf.write(data)
        tmp = tf.name
    try:
        con = sqlite3.connect(tmp)
        names = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        if not names:
            raise ValueError("No tables found in the SQLite database.")
        tables = {n: pd.read_sql_query(f'SELECT * FROM "{n}"', con) for n in names}
        con.close()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

    main = max(tables, key=lambda k: len(tables[k]))
    note = (
        f"SQLite database with {len(tables)} tables; primary table '{main}'."
        if len(tables) > 1
        else f"SQLite table '{main}'."
    )
    return tables[main], tables, "SQLite", note, main
