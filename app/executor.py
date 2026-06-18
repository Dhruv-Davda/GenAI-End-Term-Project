"""Sandboxed execution of agent-generated analysis code.

The code runs with a restricted set of builtins and an import hook that only
permits a small allow-list of data libraries — no filesystem, network, or OS
access. Execution happens on a worker thread with a hard timeout. This is a
defence-in-depth measure for a local, single-user tool, not a hardened
multi-tenant sandbox.
"""
import ast
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


class SandboxError(Exception):
    """Raised when generated code uses a disallowed construct."""


# File / network / system I/O method names that the analysis never legitimately
# needs (it operates on the provided `df`/`tables`). Blocking them statically
# closes file-read and pickle-RCE vectors that the allowed libraries otherwise
# expose. Benign methods (to_dict, to_numpy, to_string, to_datetime, …) are NOT
# listed, so normal analysis is unaffected.
_DENY_ATTRS = {
    # pandas readers (file / network)
    "read_csv", "read_table", "read_fwf", "read_excel", "read_json", "read_html",
    "read_xml", "read_parquet", "read_feather", "read_orc", "read_hdf", "read_stata",
    "read_sas", "read_spss", "read_pickle", "read_sql", "read_sql_query",
    "read_sql_table", "read_gbq", "read_clipboard",
    # pandas writers (file / network)
    "to_csv", "to_excel", "to_json", "to_parquet", "to_feather", "to_orc", "to_hdf",
    "to_stata", "to_sql", "to_gbq", "to_pickle", "to_clipboard",
    # numpy file I/O
    "load", "loadtxt", "genfromtxt", "fromfile", "tofile", "memmap", "savetxt",
    # plotly file writers
    "write_image", "write_html", "write_json",
    # process / system
    "system", "popen", "getoutput", "getstatusoutput", "check_output", "check_call",
    "Popen", "spawn", "spawnl", "spawnv",
}
_DENY_NAMES = {"open", "eval", "exec", "compile", "input", "__import__", "breakpoint", "exit", "quit"}


def _static_check(code):
    """Reject obviously dangerous constructs before execution. Raises SyntaxError
    (bad code) or SandboxError (disallowed construct)."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__") and attr.endswith("__"):
                raise SandboxError(f"access to dunder attribute '{attr}' is not allowed")
            if attr in _DENY_ATTRS:
                raise SandboxError(f"'{attr}' (file/network/system I/O) is not allowed in the sandbox")
        elif isinstance(node, ast.Name) and node.id in _DENY_NAMES:
            raise SandboxError(f"use of '{node.id}' is not allowed in the sandbox")


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
            _static_check(code)
            compiled = compile(code, "<analysis>", "exec")
        except SyntaxError:
            result["error"] = _clean_traceback(traceback.format_exc())
            return
        except SandboxError as e:
            result["error"] = f"SandboxError: {e}"
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
