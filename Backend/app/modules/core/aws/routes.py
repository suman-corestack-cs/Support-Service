from app.modules.core.aws.service import stream_aws_config_rules_inventory_across_all_regions
from app.modules.core.aws.models import AwsConfigRulesInventoryAcrossAllRegionsRequest
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File
from fastapi.responses import StreamingResponse

from app.modules.core.aws.models import GenerateAccessKeyRequest, RolePermissionsRequest
from app.modules.core.aws.service import AwsService

router = APIRouter(prefix="/core/aws", tags=["Core - Aws"])


@router.post("/bulk-tenant-creation")
async def bulk_tenant_creation(
    api_url: str = Form(...),
    auth_token: str = Form(...),
    master_account_id: str = Form(...),
    request_delay_seconds: float = Form(0.5),
    excel_file: Optional[UploadFile] = File(None),
    tenant_name_column: Optional[str] = Form(None),
    tenant_names: Optional[str] = Form(None),
):
    excel_bytes = await excel_file.read() if excel_file is not None else None
    tenant_names_list = (
        [name.strip() for name in tenant_names.split(",") if name.strip()] if tenant_names else None
    )
    generator = AwsService.stream_bulk_tenant_creation_using_excel(
        excel_bytes=excel_bytes,
        api_url=api_url,
        auth_token=auth_token,
        master_account_id=master_account_id,
        tenant_name_column=tenant_name_column,
        tenant_names=tenant_names_list,
        request_delay_seconds=request_delay_seconds,
    )
    return StreamingResponse(generator, media_type="application/x-ndjson")


@router.post("/role-permissions")
def role_permissions(request: RolePermissionsRequest):
    return StreamingResponse(AwsService.stream_get_role_permissions(request), media_type="application/x-ndjson")


@router.post("/generate-access-secret-key")
def generate_access_secret_key(request: GenerateAccessKeyRequest):
    return StreamingResponse(
        AwsService.stream_generate_access_and_secret_key(request), media_type="application/x-ndjson"
    )



@router.post("/aws-config-rules-inventory-across-all-regions")
def aws_config_rules_inventory_across_all_regions(request: AwsConfigRulesInventoryAcrossAllRegionsRequest):
    return StreamingResponse(stream_aws_config_rules_inventory_across_all_regions(request), media_type="application/x-ndjson")
