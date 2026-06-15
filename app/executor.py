"""Sandboxed execution of agent-generated analysis code.

The code runs with a restricted set of builtins and an import hook that only
permits a small allow-list of data libraries — no filesystem, network, or OS
access. Execution happens on a worker thread with a hard timeout. This is a
defence-in-depth measure for a local, single-user tool, not a hardened
multi-tenant sandbox.
"""
import builtins as _builtins
import contextlib
import io
import json
import threading
import traceback

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

from .config import EXEC_TIMEOUT

_ALLOWED_IMPORT_ROOTS = {
    "pandas", "numpy", "plotly", "math", "statistics", "datetime",
    "re", "json", "collections", "itertools", "functools", "dateutil",
    "random", "calendar", "decimal", "fractions",
}

_real_import = _builtins.__import__


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if root in _ALLOWED_IMPORT_ROOTS:
        return _real_import(name, globals, locals, fromlist, level)
    raise ImportError(f"Importing '{name}' is not permitted in the analysis sandbox.")


_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "bytes", "chr", "complex", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "getattr", "hasattr",
    "hash", "int", "isinstance", "issubclass", "iter", "len", "list", "map",
    "max", "min", "next", "ord", "pow", "print", "range", "repr", "reversed",
    "round", "set", "setattr", "slice", "sorted", "str", "sum", "tuple", "type",
    "zip", "vars",
]
_EXCEPTION_NAMES = [
    "Exception", "ValueError", "KeyError", "TypeError", "IndexError",
    "ZeroDivisionError", "AttributeError", "RuntimeError", "StopIteration",
    "ArithmeticError", "NameError", "ImportError", "NotImplementedError",
    "OverflowError", "FloatingPointError",
]

_SAFE_BUILTINS = {
    n: getattr(_builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(_builtins, n)
}
_SAFE_BUILTINS.update(
    {n: getattr(_builtins, n) for n in _EXCEPTION_NAMES if hasattr(_builtins, n)}
)
_SAFE_BUILTINS["__import__"] = _safe_import
_SAFE_BUILTINS["__build_class__"] = _builtins.__build_class__


def _clean_traceback(tb: str) -> str:
    """Drop sandbox internals, keeping frames from the analysis code."""
    lines = tb.splitlines()
    kept = [ln for ln in lines if "executor.py" not in ln and "_safe_import" not in ln]
    return "\n".join(kept) if kept else tb


def execute(code, df, tables=None):
    """Run `code` and capture stdout, an optional Plotly figure, and any error."""
    result = {"ok": False, "stdout": "", "error": None, "figure": None}

    def target():
        try:
            compiled = compile(code, "<analysis>", "exec")
        except SyntaxError:
            result["error"] = _clean_traceback(traceback.format_exc())
            return

        buf = io.StringIO()
        scope = {
            "__builtins__": _SAFE_BUILTINS,
            "pd": pd, "np": np, "px": px, "go": go, "pio": pio,
            "df": df.copy(),
            "tables": {k: v.copy() for k, v in (tables or {}).items()},
        }
        try:
            with contextlib.redirect_stdout(buf):
                exec(compiled, scope)
            result["stdout"] = buf.getvalue()
            fig = scope.get("fig")
            if (
                fig is not None
                and type(fig).__module__.split(".")[0] == "plotly"
                and hasattr(fig, "to_json")
            ):
                result["figure"] = json.loads(fig.to_json())
            result["ok"] = True
        except Exception:
            result["stdout"] = buf.getvalue()
            result["error"] = _clean_traceback(traceback.format_exc())

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(EXEC_TIMEOUT)
    if t.is_alive():
        return {
            "ok": False,
            "stdout": "",
            "error": (
                f"Execution timed out after {EXEC_TIMEOUT}s. "
                "Simplify or vectorise the computation."
            ),
            "figure": None,
        }

    result["stdout"] = (result["stdout"] or "")[:6000]
    if result["error"]:
        result["error"] = result["error"][-2500:]
    return result
