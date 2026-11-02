from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.settings.models import CreateUserGroupRequest
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.post("/create-user-group")
def create_user_group(request: CreateUserGroupRequest):
    return StreamingResponse(SettingsService.stream_create_user_groups(request), media_type="application/x-ndjson")
