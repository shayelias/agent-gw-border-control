"""Shared helper: code-line tracing, so the demo page can show the line behind each step."""
import inspect
import linecache
import os

PROJECT = os.environ["PROJECT_ID"]


def code_ref():
    """Return file:line and the source text of the caller's current line."""
    frame = inspect.currentframe().f_back
    path = frame.f_code.co_filename
    line = frame.f_lineno
    return {
        "where": f"{os.path.basename(path)}:{line}",
        "function": frame.f_code.co_name,
        "code": linecache.getline(path, line).strip(),
    }
