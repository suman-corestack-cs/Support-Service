"""Removes a script previously added via the Add Script wizard — the
reverse of file_writer.py's generate_and_register_script.

file_writer.py is deliberately append-only (see its own docstring); deleting
something inherently means touching the middle of a file, so this module
exists separately and is deliberately more cautious about it: every removal
is anchored on an exact, narrow pattern (a specific class/function name, or
a specific route path) derived the same deterministic way those names were
generated, and if a pattern isn't found (e.g. a hand-written script that
doesn't follow the generator's own naming conventions), that one step is
just skipped rather than guessed at. The two steps that work for ANY script
regardless of how its code is structured — deleting the actual scripts/*.py
file, and removing its scriptsData.js/script_sources.py entries — always
run; the Python-side cleanup (model/service/route) is best-effort on top of
that. router.py's router.include_router(...) registration is never touched:
an include'd router with zero routes left in it is completely harmless, and
figuring out whether it's genuinely safe to unregister isn't worth the risk.
"""

import re
import shutil
from datetime import datetime, timezone

from app.add_script.file_writer import AddScriptError, APP_DIR, BACKEND_ROOT, SCRIPT_SOURCES_PY, SCRIPTS_DATA_JS
from app.add_script.naming import pascal_case, snake_case

# Every file this module is about to edit gets copied here first, under a
# timestamped folder per deletion — cheap insurance against exactly the kind
# of bug this surgical-removal code is most at risk of: an anchor pattern
# matching a different, unintended span and silently corrupting or deleting
# the wrong thing. If that ever happens again, recovery is "copy the backup
# back" instead of reconstructing a file from its bytecode cache.
BACKUPS_DIR = BACKEND_ROOT / ".add_script_backups"


def _backup_files(script_id, paths):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest_dir = BACKUPS_DIR / f"{stamp}_{script_id}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path and path.exists():
            shutil.copy2(path, dest_dir / path.name)
    return dest_dir


def _skip_js_string(text, i):
    """`i` is the index of an opening quote. Returns the index just past its
    matching closing quote, honoring backslash escapes — so a quote
    character inside an escaped sequence can't be mistaken for the end of
    the string."""
    quote = text[i]
    i += 1
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return n


def _find_matching_brace(text, open_pos):
    """`open_pos` is the index of an opening '{'. Returns the index of its
    matching '}', skipping over quoted string content first — so a stray
    brace character inside a description/outputs string value (e.g.
    `"outputs": "{ name, status }"`, which is real, existing content in this
    file) can't throw off the depth count and grab the wrong span."""
    depth = 0
    i = open_pos
    n = len(text)
    while i < n:
        c = text[i]
        if c in ('"', "'", "`"):
            i = _skip_js_string(text, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _remove_block(content, anchor_pattern, next_boundary_pattern=None):
    """Removes one precisely-anchored block: from `anchor_pattern`'s match
    (plus the single blank line immediately before it, if there is one) \
    through to the next match of `next_boundary_pattern` after it, or to the
    end of the file if there's no such boundary (or none was given). Returns
    (new_content, True) if something was removed, or (content, False) if the
    anchor wasn't found at all — the caller treats "not found" as "nothing
    to clean up here", not an error, since a hand-written script's code may
    not follow the generator's own naming conventions."""
    match = re.search(anchor_pattern, content, flags=re.MULTILINE)
    if not match:
        return content, False

    start = match.start()
    if content[max(0, start - 2):start] == "\n\n":
        start -= 1  # collapse the blank line that separated it from the previous block

    if next_boundary_pattern:
        later = re.search(next_boundary_pattern, content[match.end():], flags=re.MULTILINE)
        end = match.end() + later.start() if later else len(content)
    else:
        end = len(content)

    return content[:start] + content[end:], True


def _remove_frontend_script_entry(script_id):
    """Removes exactly one entry from scriptsData.js's SCRIPTS array, located
    by its unique `id: "<script_id>"` field and then isolated via real
    brace-matching (not a naive regex up to the next "};") — necessary
    because some entries' own string values (an `outputs` field describing a
    shape like "{ name, status }") contain brace characters that would
    otherwise confuse a simpler approach. Returns the removed entry's own
    scalar fields (module/cloud/title/scriptFile/endpoint/requestType),
    parsed out of that isolated span once it's known to be self-contained."""
    content = SCRIPTS_DATA_JS.read_text(encoding="utf-8")
    id_match = re.search(rf'id:\s*"{re.escape(script_id)}"', content)
    if not id_match:
        raise AddScriptError(f"No script with id '{script_id}' found in scriptsData.js.")

    open_marker = content.rfind("\n  {\n", 0, id_match.start())
    if open_marker == -1:
        raise AddScriptError(f"Could not find the start of script '{script_id}'s entry in scriptsData.js.")
    open_pos = open_marker + 3  # the "{" itself, just past "\n  "

    close_pos = _find_matching_brace(content, open_pos)
    if close_pos == -1:
        raise AddScriptError(f"Could not find the end of script '{script_id}'s entry in scriptsData.js.")

    # Sanity check, not just a style nicety: if the id we searched for isn't
    # actually inside the span we isolated, something about this file's
    # structure doesn't match what this code assumes — stop rather than
    # remove a span that might belong to a different script's entry.
    if not (open_pos <= id_match.start() < close_pos):
        raise AddScriptError(
            f"Isolated the wrong span while looking for script '{script_id}' in scriptsData.js — not touching it."
        )

    entry_text = content[open_pos:close_pos + 1]

    def field(name):
        m = re.search(rf'{name}:\s*"((?:[^"\\]|\\.)*)"', entry_text)
        return m.group(1) if m else None

    def field_or_null(name):
        m = re.search(rf'{name}:\s*(null|"(?:[^"\\]|\\.)*")', entry_text)
        if not m or m.group(1) == "null":
            return None
        return field(name)

    fields = {
        "module": field("module"),
        "cloud": field_or_null("cloud"),
        "title": field("title"),
        "scriptFile": field("scriptFile"),
        "endpoint": field("endpoint"),
        "requestType": field("requestType"),
    }

    # Deliberately NOT open_marker itself: that's the index of the "\n" that
    # separates this entry from whatever precedes it (the previous entry's
    # "},", or "export const SCRIPTS = ["). That newline has to stay — it's
    # shared with the previous line, not part of this entry — otherwise the
    # previous entry's "}," ends up glued directly to the next entry's "{"
    # with no newline between them at all, corrupting a line that isn't even
    # the one being deleted.
    removal_start = open_marker + 1
    removal_end = close_pos + 1
    if content[removal_end:removal_end + 2] == ",\n":
        removal_end += 2
    elif content[removal_end:removal_end + 1] == ",":
        removal_end += 1

    new_content = content[:removal_start] + content[removal_end:]
    SCRIPTS_DATA_JS.write_text(new_content, encoding="utf-8")
    return fields


def _remove_script_source(script_id):
    content = SCRIPT_SOURCES_PY.read_text(encoding="utf-8")
    new_content, removed = re.subn(rf'^\s*"{re.escape(script_id)}":.*\n', "", content, flags=re.MULTILINE)
    if removed:
        SCRIPT_SOURCES_PY.write_text(new_content, encoding="utf-8")
    return bool(removed)


def delete_script(script_id):
    """Reverses generate_and_register_script for one script. Always removes
    the scriptsData.js entry, the script_sources.py entry, and the actual
    scripts/*.py file; best-effort removes the matching Pydantic model (if
    the script took a JSON body), service function, and route. Raises
    AddScriptError if the script isn't found at all. Every file this touches
    is backed up first (see BACKUPS_DIR)."""
    _backup_files(script_id, [SCRIPTS_DATA_JS, SCRIPT_SOURCES_PY])
    fields = _remove_frontend_script_entry(script_id)
    _remove_script_source(script_id)

    bundle = fields["module"]
    cloud = fields["cloud"]
    title = fields["title"]
    script_filename = fields["scriptFile"]
    endpoint = fields["endpoint"]
    request_type = fields["requestType"]

    module_dir = APP_DIR / "modules" / "settings" if bundle == "settings" else APP_DIR / "modules" / bundle / cloud
    _backup_files(script_id, [
        module_dir / "scripts" / script_filename if script_filename else None,
        module_dir / "models.py",
        module_dir / "service.py",
        module_dir / "routes.py",
    ])

    removed = {
        "script_file": False,
        "pydantic_model": False,
        "service_function": False,
        "route": False,
    }

    script_path = module_dir / "scripts" / script_filename
    if script_path.exists():
        script_path.unlink()
        removed["script_file"] = True

    route_prefix = f"/{bundle}" if bundle == "settings" else f"/{bundle}/{cloud}"
    route_path = endpoint[len(route_prefix):] if endpoint and endpoint.startswith(route_prefix) else endpoint

    if request_type == "application/json" and title:
        model_name = pascal_case(title) + "Request"
        models_path = module_dir / "models.py"
        if models_path.exists():
            content = models_path.read_text(encoding="utf-8")
            new_content, ok = _remove_block(
                content,
                rf"^class {re.escape(model_name)}\(BaseModel\):",
                r"^(class |def )",
            )
            if ok:
                models_path.write_text(new_content, encoding="utf-8")
                removed["pydantic_model"] = True

    if title:
        service_function_name = f"stream_{snake_case(title)}"
        service_path = module_dir / "service.py"
        if service_path.exists():
            content = service_path.read_text(encoding="utf-8")
            new_content, ok = _remove_block(
                content,
                rf"^def {re.escape(service_function_name)}\(",
                r"^(def |class )",
            )
            if ok:
                service_path.write_text(new_content, encoding="utf-8")
                removed["service_function"] = True

    if route_path:
        routes_path = module_dir / "routes.py"
        if routes_path.exists():
            content = routes_path.read_text(encoding="utf-8")
            new_content, ok = _remove_block(
                content,
                rf'^@router\.(get|post|put|delete)\("{re.escape(route_path)}"\)',
                r"^@router\.",
            )
            if ok:
                routes_path.write_text(new_content, encoding="utf-8")
                removed["route"] = True

    return {"script_id": script_id, "title": title, "removed": removed}
