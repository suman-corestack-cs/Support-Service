"""Wires a converted script into the running app the same way every other
script in this project was added by hand: a scripts/*.py file, a Pydantic
request model (or Form/File params for uploads), a service wrapper, a route,
a script_sources.py entry, a router.py registration if the bundle/cloud
combo isn't wired up yet, and a scriptsData.js entry.

Every edit here is either "write a brand-new file" or "append near a known,
unambiguous boundary" (end of file, just before a dict/array's closing
bracket, or a fresh import line) — never a mid-body/mid-class insertion —
specifically so this stays safe to run unattended on files this process
didn't write.
"""

import re
from pathlib import Path

from app.add_script.js_literal import JSIdentifier, to_js_literal
from app.add_script.naming import pascal_case, slugify, snake_case, title_case_filename

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = BACKEND_ROOT / "app"
FRONTEND_ROOT = BACKEND_ROOT.parent / "Frontend"
SCRIPTS_DATA_JS = FRONTEND_ROOT / "src" / "scriptsData.js"
ROUTER_PY = APP_DIR / "router.py"
SCRIPT_SOURCES_PY = APP_DIR / "script_sources.py"

VALID_BUNDLES = {"core", "finops", "secops", "cloudops", "reports", "settings"}
VALID_CLOUDS = {"aws", "azure", "gcp", "oci", "multicloud"}

_PY_TYPE_FOR_INPUT = {
    "number": "float",
    "toggle": "bool",
    "list": "List[str]",
    "file": "bytes",  # only used for the service-function signature; the route itself takes UploadFile
}


class AddScriptError(ValueError):
    """Raised for anything that's the caller's fault (bad bundle/cloud,
    duplicate script id, ...) rather than an internal bug."""


def module_dir(bundle, cloud):
    if bundle == "settings":
        return APP_DIR / "modules" / "settings"
    return APP_DIR / "modules" / bundle / cloud


def module_import_path(bundle, cloud):
    """The bundle/cloud suffix used in `from app.modules.<this>.xxx import
    ...` — callers that need the fully-qualified module path prepend
    "app.modules." themselves."""
    return "settings" if bundle == "settings" else f"{bundle}.{cloud}"


def route_prefix(bundle, cloud):
    return f"/{bundle}" if bundle == "settings" else f"/{bundle}/{cloud}"


def ensure_imports(file_path, import_lines):
    """Prepends whichever of `import_lines` aren't already present verbatim
    anywhere in the file. Safe: only ever adds lines, never touches existing
    ones, and Python tolerates import statements in any order/grouping."""
    content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
    missing = [line for line in import_lines if line not in content]
    if missing:
        file_path.write_text("\n".join(missing) + "\n" + content, encoding="utf-8")


def ensure_module_scaffolded(bundle, cloud):
    """Creates the module's models.py/service.py/routes.py/scripts/ if this
    bundle+cloud combo has never been touched before — mirroring the minimal
    stub shape this project's own folder-structure setup already used."""
    mdir = module_dir(bundle, cloud)
    scripts_dir = mdir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    models_path = mdir / "models.py"
    service_path = mdir / "service.py"
    routes_path = mdir / "routes.py"

    if not models_path.exists():
        models_path.write_text("from pydantic import BaseModel\n", encoding="utf-8")
    if not service_path.exists():
        service_path.write_text("", encoding="utf-8")
    if not routes_path.exists():
        tag = "Settings" if bundle == "settings" else f"{bundle.capitalize()} - {cloud.capitalize()}"
        routes_path.write_text(
            f'from fastapi import APIRouter\n\nrouter = APIRouter(prefix="{route_prefix(bundle, cloud)}", tags=["{tag}"])\n',
            encoding="utf-8",
        )
    return models_path, service_path, routes_path, scripts_dir


def _ordered_params(analysis):
    """The converted function's own parameters, in form order — every one
    of them comes from analysis.extra_inputs now; nothing is added
    automatically."""
    return [
        {"name": inp.name, "input_type": inp.type, "required": inp.required, "default": inp.default}
        for inp in analysis.extra_inputs
    ]


def _py_type(input_type):
    return _PY_TYPE_FOR_INPUT.get(input_type, "str")


def write_script_file(scripts_dir, filename, code):
    path = scripts_dir / filename
    if path.exists():
        raise AddScriptError(f"A script file named {filename} already exists in this bundle/cloud — pick a different script name.")
    path.write_text(code if code.endswith("\n") else code + "\n", encoding="utf-8")
    return path


def append_pydantic_model(models_path, model_name, params):
    non_file_params = [p for p in params if p["input_type"] != "file"]
    needs_optional = any(not p["required"] for p in non_file_params)
    needs_list = any(p["input_type"] == "list" for p in non_file_params)

    imports = []
    typing_names = [n for n, needed in [("Optional", needs_optional), ("List", needs_list)] if needed]
    if typing_names:
        imports.append(f"from typing import {', '.join(typing_names)}")
    imports.append("from pydantic import BaseModel")
    ensure_imports(models_path, imports)

    lines = [f"\n\nclass {model_name}(BaseModel):"]
    if not non_file_params:
        lines.append("    pass")
    for p in non_file_params:
        type_hint = _py_type(p["input_type"])
        if p["required"]:
            lines.append(f"    {p['name']}: {type_hint}")
        else:
            default_repr = "None" if p["default"] is None else repr(p["default"])
            lines.append(f"    {p['name']}: Optional[{type_hint}] = {default_repr}")

    with models_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _script_accepts_progress_callback(converted_script_code, function_name):
    """Whether the converted function's own signature declares
    progress_callback — determined from the actual generated code, not a
    separate flag, so it can never drift out of sync with what Claude
    actually wrote. A script with no natural per-item loop legitimately
    omits this parameter, and calling it with progress_callback anyway
    would crash with 'unexpected keyword argument'."""
    match = re.search(rf"def\s+{re.escape(function_name)}\s*\(([^)]*)\)", converted_script_code)
    return bool(match) and "progress_callback" in match.group(1)


def append_service_function(service_path, *, service_function_name, script_module_stem, script_function_name, request_model_name, params, module_import, supports_progress_callback):
    file_params = [p for p in params if p["input_type"] == "file"]
    imports = ["from app import execution", f"from app.modules.{module_import}.scripts.{script_module_stem} import {script_function_name}"]
    if request_model_name:
        imports.append(f"from app.modules.{module_import}.models import {request_model_name}")
    ensure_imports(service_path, imports)

    progress_kwarg_line = "            progress_callback=progress_callback,\n" if supports_progress_callback else ""

    if request_model_name:
        # JSON-body case: one `request` object, destructured by attribute.
        call_lines = "\n".join(f"            {p['name']}=request.{p['name']}," for p in params)
        code = (
            f"\n\ndef {service_function_name}(request: {request_model_name}):\n"
            f"    def run(progress_callback):\n"
            f"        return {script_function_name}(\n"
            f"{call_lines}\n"
            f"{progress_kwarg_line}"
            f"        )\n\n"
            f"    return execution.stream(run)\n"
        )
    else:
        # Multipart case: plain keyword params, file fields arrive as raw bytes.
        sig_parts = []
        call_lines = []
        for p in params:
            if p["input_type"] == "file":
                sig_parts.append(f"{p['name']}_bytes: bytes = None")
                call_lines.append(f"            {p['name']}=io.BytesIO({p['name']}_bytes) if {p['name']}_bytes is not None else None,")
            elif p["required"]:
                sig_parts.append(f"{p['name']}: {_py_type(p['input_type'])}")
                call_lines.append(f"            {p['name']}={p['name']},")
            else:
                default_repr = "None" if p["default"] is None else repr(p["default"])
                sig_parts.append(f"{p['name']}: {_py_type(p['input_type'])} = {default_repr}")
                call_lines.append(f"            {p['name']}={p['name']},")
        if file_params:
            ensure_imports(service_path, ["import io"])
        code = (
            f"\n\ndef {service_function_name}({', '.join(sig_parts)}):\n"
            f"    def run(progress_callback):\n"
            f"        return {script_function_name}(\n"
            + "\n".join(call_lines) + "\n"
            f"{progress_kwarg_line}"
            f"        )\n\n"
            f"    return execution.stream(run)\n"
        )

    with service_path.open("a", encoding="utf-8") as f:
        f.write(code)


def append_route(routes_path, *, route_path, route_function_name, service_function_name, request_model_name, module_import, params):
    imports = ["from fastapi.responses import StreamingResponse", f"from app.modules.{module_import}.service import {service_function_name}"]

    if request_model_name:
        imports.append(f"from app.modules.{module_import}.models import {request_model_name}")
        ensure_imports(routes_path, imports)
        code = (
            f'\n\n@router.post("{route_path}")\n'
            f"def {route_function_name}(request: {request_model_name}):\n"
            f"    return StreamingResponse({service_function_name}(request), media_type=\"application/x-ndjson\")\n"
        )
    else:
        needs_optional = any(p["input_type"] == "file" or not p["required"] for p in params)
        fastapi_names = ["Form", "UploadFile", "File"]
        imports.append(f"from fastapi import {', '.join(fastapi_names)}")
        if needs_optional:
            imports.append("from typing import Optional")
        ensure_imports(routes_path, imports)

        sig_parts = []
        call_kwargs = []
        pre_lines = []
        for p in params:
            if p["input_type"] == "file":
                sig_parts.append(f"{p['name']}: Optional[UploadFile] = File(None)")
                pre_lines.append(f"    {p['name']}_bytes = await {p['name']}.read() if {p['name']} is not None else None")
                call_kwargs.append(f"        {p['name']}_bytes={p['name']}_bytes,")
            elif p["required"]:
                sig_parts.append(f"{p['name']}: {_py_type(p['input_type'])} = Form(...)")
                call_kwargs.append(f"        {p['name']}={p['name']},")
            else:
                default_repr = "None" if p["default"] is None else repr(p["default"])
                sig_parts.append(f"{p['name']}: Optional[{_py_type(p['input_type'])}] = Form({default_repr})")
                call_kwargs.append(f"        {p['name']}={p['name']},")

        code = (
            f'\n\n@router.post("{route_path}")\n'
            f"async def {route_function_name}(\n    " + ",\n    ".join(sig_parts) + ",\n):\n"
            + ("\n".join(pre_lines) + "\n" if pre_lines else "")
            + f"    generator = {service_function_name}(\n" + "\n".join(call_kwargs) + "\n    )\n"
            f"    return StreamingResponse(generator, media_type=\"application/x-ndjson\")\n"
        )

    with routes_path.open("a", encoding="utf-8") as f:
        f.write(code)


def ensure_router_registered(bundle, cloud):
    """If this bundle/cloud's routes.py isn't yet included in router.py
    (true for any combo no script has ever used before), append the import
    + include_router() call. Existing entries are never touched."""
    content = ROUTER_PY.read_text(encoding="utf-8")
    module_import = module_import_path(bundle, cloud)
    router_alias = f"{bundle}_{cloud}_router" if bundle != "settings" else "settings_router"
    import_line = f"from app.modules.{module_import}.routes import router as {router_alias}"
    if import_line in content:
        return False  # already wired up

    include_line = f"router.include_router({router_alias})"
    new_content = content.rstrip("\n") + f"\n{import_line}\n" + f"\n{include_line}\n"
    ROUTER_PY.write_text(new_content, encoding="utf-8")
    return True


def append_script_source(script_id, script_path):
    content = SCRIPT_SOURCES_PY.read_text(encoding="utf-8")
    if f'"{script_id}"' in content:
        raise AddScriptError(f"A script with id '{script_id}' is already registered in script_sources.py.")

    rel_path = script_path.relative_to(APP_DIR).as_posix()
    new_line = f'    "{script_id}": _APP_DIR / "{rel_path}",\n'
    # Insert right before the dict's closing "}" (the line that is just "}").
    match = re.search(r"\n}\n", content)
    if not match:
        raise AddScriptError("Could not find SCRIPT_SOURCES' closing brace in script_sources.py — not touching it.")
    insert_at = match.start() + 1
    new_content = content[:insert_at] + new_line + content[insert_at:]
    SCRIPT_SOURCES_PY.write_text(new_content, encoding="utf-8")


def _build_frontend_inputs(analysis, params, request_type):
    """The scriptsData.js `inputs[]` array — every input Claude identified,
    shown in the UI exactly as declared (a plain field of its own type, no
    automatic dropdown substitution), each carrying an info-icon description
    exactly like every hand-built script's inputs already do."""
    inputs = []
    for inp in analysis.extra_inputs:
        entry = {"name": inp.name, "label": inp.label, "type": inp.type, "required": inp.required}
        if inp.description:
            entry["description"] = inp.description
        if inp.default is not None:
            entry["default"] = inp.default
        if inp.type == "select" and inp.options:
            entry["options"] = [{"value": o.value, "label": o.label} for o in inp.options]
        inputs.append(entry)

    return inputs


# Field names the "Decrypt Secret Key" panel can fill (see
# AZURE_DECRYPT_SECRET_COMPANION_PANEL.applyValues in scriptsData.js). An
# Azure script taking a secret plus a tenant or app id gets the panel even if
# Claude didn't flag it.
_AZURE_SECRET_FIELDS = {"application_secret", "client_secret", "app_secret"}
_AZURE_ID_FIELDS = {"tenant_id", "azure_tenant_id", "directory_id", "application_id", "app_id", "client_id"}


def _wants_azure_secret_panel(cloud, analysis):
    if cloud != "azure":
        return False
    if analysis.needs_azure_secret_panel:
        return True
    names = {inp.name for inp in analysis.extra_inputs}
    return bool(names & _AZURE_SECRET_FIELDS) and bool(names & _AZURE_ID_FIELDS)


def append_frontend_script_entry(*, script_id, bundle, cloud, title, script_filename, description, method, endpoint, request_type, inputs, outputs_description, needs_generate_keys_panel, needs_azure_secret_panel=False):
    content = SCRIPTS_DATA_JS.read_text(encoding="utf-8")
    if f'"{script_id}"' in content:
        raise AddScriptError(f"A script with id '{script_id}' is already registered in scriptsData.js.")

    entry = {
        "id": script_id,
        "module": bundle,
        "cloud": cloud,
        "title": title,
        "scriptFile": script_filename,
        "description": description,
        "method": method,
        "endpoint": endpoint,
        "requestType": request_type,
        "inputs": inputs,
        "outputs": outputs_description,
    }
    if needs_azure_secret_panel:
        entry["companionPanel"] = JSIdentifier("AZURE_DECRYPT_SECRET_COMPANION_PANEL")
    elif needs_generate_keys_panel:
        entry["companionPanel"] = JSIdentifier("GENERATE_ACCESS_KEY_COMPANION_PANEL")

    entry_code = to_js_literal(entry, indent=2, _level=1)
    new_entry_text = f"  {entry_code},\n"

    # Insert right before the SCRIPTS array's closing "];" — searched for only
    # AFTER "export const SCRIPTS = [", since scriptsData.js declares more than
    # one array that closes with "];" (e.g. ENVIRONMENTS earlier in the file);
    # searching the whole file would match the first one instead of SCRIPTS'.
    scripts_decl = content.find("export const SCRIPTS = [")
    if scripts_decl == -1:
        raise AddScriptError("Could not find 'export const SCRIPTS = [' in scriptsData.js — not touching it.")
    match = re.search(r"\n\];\n", content[scripts_decl:])
    if not match:
        raise AddScriptError("Could not find the SCRIPTS array's closing bracket in scriptsData.js — not touching it.")
    insert_at = scripts_decl + match.start() + 1
    new_content = content[:insert_at] + new_entry_text + content[insert_at:]
    SCRIPTS_DATA_JS.write_text(new_content, encoding="utf-8")


def generate_and_register_script(*, script_name, bundle, cloud, description, analysis):
    """Orchestrates every file edit for one newly-analyzed script. Returns a
    dict summary. Raises AddScriptError for anything the caller should see
    as a clean 4xx (bad input, id collision) rather than a 500."""
    bundle = bundle.strip().lower()
    cloud = (cloud or "").strip().lower() or None
    if bundle not in VALID_BUNDLES:
        raise AddScriptError(f"Unknown bundle '{bundle}'. Valid: {', '.join(sorted(VALID_BUNDLES))}")
    if bundle != "settings":
        if not cloud or cloud not in VALID_CLOUDS:
            raise AddScriptError(f"Unknown cloud '{cloud}'. Valid: {', '.join(sorted(VALID_CLOUDS))}")
    elif cloud:
        raise AddScriptError("The 'settings' bundle has no cloud dimension — leave Cloud unset.")

    module_import = module_import_path(bundle, cloud)
    script_id = f"{bundle}-{cloud}-{slugify(script_name)}" if cloud else f"{bundle}-{slugify(script_name)}"

    models_path, service_path, routes_path, scripts_dir = ensure_module_scaffolded(bundle, cloud)

    script_filename = title_case_filename(script_name)
    write_script_file(scripts_dir, script_filename, analysis.converted_script_code)
    script_module_stem = script_filename[:-3]

    params = _ordered_params(analysis)
    has_file_params = any(p["input_type"] == "file" for p in params)
    request_type = "multipart/form-data" if has_file_params else "application/json"

    request_model_name = None
    if not has_file_params:
        request_model_name = pascal_case(script_name) + "Request"
        append_pydantic_model(models_path, request_model_name, params)

    service_function_name = f"stream_{snake_case(script_name)}"
    append_service_function(
        service_path,
        service_function_name=service_function_name,
        script_module_stem=script_module_stem,
        script_function_name=analysis.function_name,
        request_model_name=request_model_name,
        params=params,
        module_import=module_import,
        supports_progress_callback=_script_accepts_progress_callback(analysis.converted_script_code, analysis.function_name),
    )

    route_path = f"/{slugify(script_name)}"
    endpoint_path = f"{route_prefix(bundle, cloud)}{route_path}"
    route_function_name = snake_case(script_name)
    append_route(
        routes_path,
        route_path=route_path,
        route_function_name=route_function_name,
        service_function_name=service_function_name,
        request_model_name=request_model_name,
        module_import=module_import,
        params=params,
    )

    newly_registered = ensure_router_registered(bundle, cloud)
    append_script_source(script_id, scripts_dir / script_filename)

    frontend_inputs = _build_frontend_inputs(analysis, params, request_type)
    append_frontend_script_entry(
        script_id=script_id,
        bundle=bundle,
        cloud=cloud,
        title=script_name,
        script_filename=script_filename,
        description=analysis.summary,
        method="POST",
        endpoint=endpoint_path,
        request_type=request_type,
        inputs=frontend_inputs,
        outputs_description=analysis.outputs_description,
        needs_generate_keys_panel=analysis.needs_generate_keys_panel,
        needs_azure_secret_panel=_wants_azure_secret_panel(cloud, analysis),
    )

    return {
        "script_id": script_id,
        "endpoint": endpoint_path,
        "script_file": str((scripts_dir / script_filename).relative_to(BACKEND_ROOT)),
        "router_newly_registered": newly_registered,
        "summary": analysis.summary,
    }
