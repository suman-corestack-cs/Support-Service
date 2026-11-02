from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.secops.multicloud.models import BulkComplianceStandardsExecutionRequest
from app.modules.secops.multicloud.service import MulticloudService

router = APIRouter(prefix="/secops/multicloud", tags=["Secops - Multicloud"])


@router.post("/bulk-compliance-standards-execution")
def bulk_compliance_standards_execution(request: BulkComplianceStandardsExecutionRequest):
    generator = MulticloudService.stream_bulk_compliance_standards_execution(request)
    return StreamingResponse(generator, media_type="application/x-ndjson")
