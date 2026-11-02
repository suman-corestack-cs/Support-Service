from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.core.multicloud.models import BulkSyncStatusRequest
from app.modules.core.multicloud.service import MulticloudService

router = APIRouter(prefix="/core/multicloud", tags=["Core - Multicloud"])


@router.post("/bulk-sync-status")
def bulk_sync_status(request: BulkSyncStatusRequest):
    return StreamingResponse(MulticloudService.stream_bulk_sync_status(request), media_type="application/x-ndjson")
