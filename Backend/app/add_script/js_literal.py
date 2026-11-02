"""A tiny JS-object-literal serializer — like json.dumps, but lets specific
values come out as bare identifiers (e.g. `loadOptions: loadMasterAccountNames`,
`companionPanel: GENERATE_ACCESS_KEY_COMPANION_PANEL`) instead of quoted
strings, since the generated scriptsData.js entry needs to reference real,
already-defined functions/constants rather than re-describe them."""

import json


class JSIdentifier(str):
    """Marks a string that should be emitted unquoted, as a raw identifier
    (a function/constant name), not a JS string literal."""


def to_js_literal(value, indent=2, _level=0):
    pad = " " * (indent * (_level + 1))
    closing_pad = " " * (indent * _level)

    if isinstance(value, JSIdentifier):
        return str(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        items = ",\n".join(f"{pad}{to_js_literal(v, indent, _level + 1)}" for v in value)
        return f"[\n{items},\n{closing_pad}]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = ",\n".join(f"{pad}{_key(k)}: {to_js_literal(v, indent, _level + 1)}" for k, v in value.items())
        return f"{{\n{items},\n{closing_pad}}}"
    raise TypeError(f"Cannot serialize {type(value)} to a JS literal")


def _key(key):
    # A plain identifier-safe key can go unquoted (nicer diffs / matches
    # this codebase's own style); anything else gets quoted.
    import re

    return key if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", key) else json.dumps(key)
