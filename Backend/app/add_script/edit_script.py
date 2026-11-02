"""Saves an in-browser edit of an existing script's source file, with
Claude reviewing the edit first.

Flow: Claude compares the edited code against the current file. Syntax
errors (missing colon, unbalanced bracket, bad indentation, ...) are fixed
automatically — and nothing else is touched. Any other definite mistake
(undefined name, missing import, a function the app imports was renamed or
its parameters no longer match how the app calls it, ...) is reported back
and the file is NOT written, so a broken edit can never replace a working
script. On top of Claude's review, the final code is always re-checked
locally (it must parse, and every name the app imports from this module
must still exist with compatible parameters) before it is saved.

Only scripts in script_sources.py's allowlist can be edited, so this can
never write an arbitrary file on the server. With `uvicorn --reload` the
saved script is picked up immediately; otherwise restart the backend."""

import ast
import os
import tempfile
from pathlib import Path

from app.add_script.code_generation import call_claude_for_json
from app.script_sources import get_script_source_path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
APP_DIR = BACKEND_DIR / "app"


class ScriptNotFoundError(Exception):
    pass


class ScriptEditRejected(Exception):
    """The edit has mistakes that weren't auto-fixable. `source` is the
    edited code with any syntax fixes already applied, so the editor can
    show it back to the user instead of losing those fixes."""

    def __init__(self, message, errors, source, syntax_fixes):
        super().__init__(message)
        self.message = message
        self.errors = errors
        self.source = source
        self.syntax_fixes = syntax_fixes


SYSTEM_PROMPT = """You review an edit someone made by hand to a Python script that's part of an internal \
FastAPI tool. The app imports functions from this script and calls them; you're shown exactly which names it \
imports and the code that calls them.

You have exactly two jobs:

1. Fix SYNTAX errors only — anything that stops Python from parsing the file: a missing colon, unbalanced \
brackets/parentheses/quotes, inconsistent or wrong indentation, a stray character, a misspelled keyword \
(e.g. `retrun`, `esle`), an unterminated string, etc. Make the smallest possible change that fixes each one. \
Do NOT change anything else: no refactoring, no renaming, no reformatting, no "improvements", no logic \
changes, even if you'd write it differently. If the edited code has no syntax errors, do not return any code.

2. Report other DEFINITE mistakes that would make the script crash or stop working when the app runs it — \
for example: a name used but never defined or imported, a module used but not imported, a function the app \
imports was removed or renamed, a function's parameters no longer accept the arguments the app passes it, \
calling something with the wrong number of arguments, a variable used before assignment. Do NOT fix these — \
only describe them, with the line number, so the person can fix them. Do NOT report style issues, possible \
improvements, missing error handling, hardcoded values, or anything you're not sure is an actual bug. If \
the person intentionally changed behavior (e.g. a different URL, a new field, different filtering), that's \
their choice — not a mistake.

Respond with ONLY a single JSON object — no markdown code fences, no commentary — exactly this shape:
{
  "has_syntax_errors": true or false,
  "fixed_code": "the full edited file with ONLY the syntax errors fixed, as one string with real newlines — or null if there were no syntax errors",
  "syntax_fixes": ["line N: what was wrong and how it was fixed", ...],
  "errors": ["line N: description of a definite non-syntax mistake", ...],
  "summary": "one plain-English sentence describing what the edit changed"
}"""


def _module_name(path):
    return ".".join(path.resolve().relative_to(BACKEND_DIR).with_suffix("").parts)


def _find_importers(script_path):
    """Returns ({imported_name, ...}, [(relative_path, source), ...]) for every
    file under app/ that does `from <this script's module> import ...`."""
    module = _module_name(script_path)
    names, importers = set(), []
    for py_file in APP_DIR.rglob("*.py"):
        if py_file.resolve() == script_path.resolve():
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if module not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == module:
                names.update(alias.name for alias in node.names)
                found = True
        if found:
            importers.append((str(py_file.relative_to(BACKEND_DIR)), source))
    return names, importers


def _top_level_definitions(tree):
    """Name -> node for every top-level function, class, or assignment."""
    defs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    defs[target.id] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                defs[(alias.asname or alias.name).split(".")[0]] = node
    return defs


def _params(func):
    args = func.args
    positional = args.posonlyargs + args.args
    required = {a.arg for a in positional[: len(positional) - len(args.defaults)]}
    required |= {a.arg for a, d in zip(args.kwonlyargs, args.kw_defaults) if d is None}
    all_names = {a.arg for a in positional + args.kwonlyargs}
    return all_names, required, args.kwarg is not None


def _check_app_compatibility(original_source, new_source, imported_names):
    """Every name the app imports must still exist, and imported functions
    must still accept every parameter they used to (so existing calls keep
    working) without demanding any new required parameter."""
    errors = []
    try:
        old_defs = _top_level_definitions(ast.parse(original_source))
    except SyntaxError:
        old_defs = {}
    new_defs = _top_level_definitions(ast.parse(new_source))

    for name in sorted(imported_names):
        if name not in new_defs:
            errors.append(f"'{name}' no longer exists, but the app imports it — restore it or keep the same name.")
            continue
        old, new = old_defs.get(name), new_defs[name]
        func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
        if not (isinstance(old, func_types) and isinstance(new, func_types)):
            continue
        old_all, _, _ = _params(old)
        new_all, new_required, new_has_kwargs = _params(new)
        missing = sorted(old_all - new_all) if not new_has_kwargs else []
        if missing:
            errors.append(
                f"line {new.lineno}: '{name}' no longer accepts parameter(s) {', '.join(missing)}, "
                f"which the app passes to it."
            )
        added_required = sorted(new_required - old_all)
        if added_required:
            errors.append(
                f"line {new.lineno}: '{name}' now requires new parameter(s) {', '.join(added_required)} that the "
                f"app doesn't pass — give them a default value."
            )
    return errors


def _syntax_error_text(e):
    return f"line {e.lineno}: {e.msg}" + (f" → {e.text.strip()}" if e.text else "")


def _write_atomically(path, content):
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def review_and_save_script(script_id, edited_source):
    """Returns {"saved": bool, "source", "syntax_fixes", "summary"}. Raises
    ScriptNotFoundError, ScriptEditRejected, or RuntimeError (Claude call
    failed)."""
    path = get_script_source_path(script_id)
    if not path or not path.is_file():
        raise ScriptNotFoundError(f"No editable script with id '{script_id}'.")

    original_source = path.read_text(encoding="utf-8")
    edited_source = edited_source.replace("\r\n", "\n")
    if edited_source == original_source:
        return {"saved": False, "source": original_source, "syntax_fixes": [], "summary": "No changes to save."}

    try:
        ast.parse(edited_source)
        local_syntax_error = None
    except SyntaxError as e:
        local_syntax_error = _syntax_error_text(e)

    imported_names, importers = _find_importers(path)
    user_text = [
        f"Names the app imports from this script: {', '.join(sorted(imported_names)) or '(none)'}",
        f"Python's own parser says: {local_syntax_error or 'no syntax errors'}",
    ]
    for rel_path, source in importers:
        user_text.append(f"--- App code that imports and calls this script: {rel_path} ---\n```python\n{source}\n```")
    user_text.append(f"--- CURRENT saved version of {path.name} (before the edit) ---\n```python\n{original_source}\n```")
    user_text.append(f"--- EDITED version of {path.name} (review this one) ---\n```python\n{edited_source}\n```")

    review = call_claude_for_json(
        system_prompt=SYSTEM_PROMPT,
        user_content=[{"type": "text", "text": "\n\n".join(user_text)}],
        feature_name="Edit Script",
    )

    syntax_fixes = [str(s) for s in (review.get("syntax_fixes") or [])]
    errors = [str(e) for e in (review.get("errors") or [])]
    fixed_code = review.get("fixed_code")

    # Only take Claude's rewritten code when the file genuinely didn't parse —
    # a file that already parses is saved exactly as the person wrote it.
    final_source = edited_source
    if local_syntax_error:
        if isinstance(fixed_code, str) and fixed_code.strip():
            final_source = fixed_code.replace("\r\n", "\n")
            if not final_source.endswith("\n") and edited_source.endswith("\n"):
                final_source += "\n"
        else:
            syntax_fixes = []
    else:
        syntax_fixes = []

    try:
        ast.parse(final_source)
    except SyntaxError as e:
        raise ScriptEditRejected(
            "The script still has a syntax error that couldn't be fixed automatically.",
            [_syntax_error_text(e)] + errors,
            final_source,
            syntax_fixes,
        )

    errors += [e for e in _check_app_compatibility(original_source, final_source, imported_names) if e not in errors]
    if errors:
        raise ScriptEditRejected(
            "Not saved — Claude found mistakes in the edit that need to be fixed first.",
            errors,
            final_source,
            syntax_fixes,
        )

    _write_atomically(path, final_source)
    return {
        "saved": True,
        "source": final_source,
        "syntax_fixes": syntax_fixes,
        "summary": str(review.get("summary") or ""),
    }
