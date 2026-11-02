from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.add_script.code_generation import analyze_and_convert_script
from app.add_script.delete_script import delete_script
from app.add_script.edit_script import ScriptEditRejected, ScriptNotFoundError, review_and_save_script
from app.add_script.file_writer import AddScriptError, generate_and_register_script

router = APIRouter(prefix="/admin", tags=["Admin"])

_ALLOWED_OUTPUT_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".txt")


@router.post("/add-script")
async def add_script(
    script_name: str = Form(...),
    bundle: str = Form(...),
    cloud: Optional[str] = Form(None),
    description: str = Form(""),
    script_files: List[UploadFile] = File(...),
    output_files: List[UploadFile] = File([]),
):
    """Analyzes one or more uploaded Python scripts (plus an optional sample
    of their output, and an optional description — both just extra context
    for Claude, neither required) with Claude, converts them into an
    API-ready script the same way every other script in this project was
    added by hand, and wires the result into the backend (new scripts/*.py
    file, Pydantic model or Form/File route, service wrapper, route,
    script_sources.py entry, router.py registration if needed) and the
    frontend (scriptsData.js entry). A backend restart is required
    afterward for the new route to actually come online — this endpoint
    only writes the files."""
    for f in script_files:
        if not f.filename or not f.filename.lower().endswith(".py"):
            raise HTTPException(status_code=400, detail=f"'{f.filename}' isn't a .py file — only Python scripts are accepted here.")

    named_output_files = [f for f in output_files if f.filename]
    for f in named_output_files:
        if not f.filename.lower().endswith(_ALLOWED_OUTPUT_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"'{f.filename}' isn't an accepted output sample format — use Excel (.xlsx/.xls/.xlsm), text (.txt/.csv/.tsv), or PDF.",
            )

    script_file_contents = [(f.filename, await f.read()) for f in script_files]
    output_file_contents = [(f.filename, await f.read()) for f in named_output_files]

    try:
        analysis = analyze_and_convert_script(
            script_name=script_name,
            bundle=bundle,
            cloud=cloud,
            description=description,
            script_files=script_file_contents,
            output_files=output_file_contents,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        result = generate_and_register_script(
            script_name=script_name,
            bundle=bundle,
            cloud=cloud,
            description=description,
            analysis=analysis,
        )
    except AddScriptError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


class EditScriptRequest(BaseModel):
    source: str


@router.put("/scripts/{script_id}/source")
def edit_script_source(script_id: str, request: EditScriptRequest):
    """Saves an edit made in the View Script modal. Claude reviews it first:
    syntax errors are fixed automatically, any other definite mistake is
    returned as a 422 (with the syntax-fixed code) and nothing is written.
    A plain `def` so the long Claude call runs in FastAPI's threadpool
    instead of blocking the event loop."""
    try:
        return review_and_save_script(script_id, request.source)
    except ScriptNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ScriptEditRejected as e:
        raise HTTPException(
            status_code=422,
            detail={"message": e.message, "errors": e.errors, "source": e.source, "syntax_fixes": e.syntax_fixes},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/scripts/{script_id}")
async def remove_script(script_id: str):
    """Reverses add_script for one script: removes its scriptsData.js and
    script_sources.py entries and its scripts/*.py file (always), plus its
    generated Pydantic model/service function/route on a best-effort basis
    (skipped, not an error, for anything that doesn't match the generator's
    own naming conventions — e.g. a hand-written script). A backend restart
    is required afterward, same as adding one, for the route to actually
    come off the running app."""
    try:
        return delete_script(script_id)
    except AddScriptError as e:
        raise HTTPException(status_code=404, detail=str(e))
