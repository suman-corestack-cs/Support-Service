from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.core.azure.models import DecryptAzureSecretRequest
from app.modules.core.azure.service import AzureService

router = APIRouter(prefix="/core/azure", tags=["Core - Azure"])


@router.post("/decrypt-application-secret")
def decrypt_application_secret(request: DecryptAzureSecretRequest):
    return StreamingResponse(
        AzureService.stream_decrypt_azure_application_secret(request), media_type="application/x-ndjson"
    )
