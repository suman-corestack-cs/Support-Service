from app.modules.core.aws.scripts.Aws_Config_Rules_Inventory_Across_All_Regions import get_config_rules_all_regions
from app.modules.core.aws.models import AwsConfigRulesInventoryAcrossAllRegionsRequest
import io

from app import execution
from app.modules.core.aws.models import GenerateAccessKeyRequest, RolePermissionsRequest
from app.modules.core.aws.scripts.Bulck_tenant_creations_using_excel import (
    bulk_tenant_creation_using_excel,
)
from app.modules.core.aws.scripts.Generate_access_key_and_secret_key import (
    generate_access_and_secret_key,
)
from app.modules.core.aws.scripts.Get_role_permission import get_role_permissions
from app.sts_config import get_sts_credentials


class AwsService:
    @staticmethod
    def stream_bulk_tenant_creation_using_excel(
        api_url: str,
        auth_token: str,
        master_account_id: str,
        request_delay_seconds: float = 0.5,
        excel_bytes: bytes = None,
        tenant_name_column: str = None,
        tenant_names: list = None,
    ):
        def run(progress_callback):
            return bulk_tenant_creation_using_excel(
                excel_file=io.BytesIO(excel_bytes) if excel_bytes is not None else None,
                api_url=api_url,
                auth_token=auth_token,
                master_account_id=master_account_id,
                tenant_name_column=tenant_name_column,
                tenant_names=tenant_names,
                request_delay_seconds=request_delay_seconds,
                progress_callback=progress_callback,
            )

        return execution.stream(run)

    @staticmethod
    def stream_get_role_permissions(request: RolePermissionsRequest):
        def run(progress_callback):
            return get_role_permissions(
                request.access_key,
                request.secret_key,
                request.session_token,
                request.role_name,
                progress_callback=progress_callback,
            )

        return execution.stream(run)

    @staticmethod
    def stream_generate_access_and_secret_key(request: GenerateAccessKeyRequest):
        def run(progress_callback):
            sts_credentials = get_sts_credentials()
            return generate_access_and_secret_key(
                aws_access_key_id=sts_credentials["access_key_id"],
                aws_secret_access_key=sts_credentials["secret_access_key"],
                role_arn=request.role_arn,
                role_session_name=request.role_session_name,
                external_id=request.external_id,
                region_name=sts_credentials["region_name"],
            )

        return execution.stream(run)



def stream_aws_config_rules_inventory_across_all_regions(request: AwsConfigRulesInventoryAcrossAllRegionsRequest):
    def run(progress_callback):
        return get_config_rules_all_regions(
            access_key=request.access_key,
            secret_key=request.secret_key,
            session_token=request.session_token,
            progress_callback=progress_callback,
        )

    return execution.stream(run)
