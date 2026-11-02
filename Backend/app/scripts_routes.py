from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.script_sources import get_script_source_path

router = APIRouter(prefix="/scripts", tags=["Scripts"])


@router.get("/{script_id}/source", response_class=PlainTextResponse)
def get_script_source(script_id: str):
    path = get_script_source_path(script_id)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="Script source not found")
    return path.read_text(encoding="utf-8")
