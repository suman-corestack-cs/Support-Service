from app import execution
from app.modules.finops.azure.scripts.Azure_Ea_Account_Billing_Periods_Details import get_azure_billing_periods
from app.modules.finops.azure.models import AzureEaAccountBillingPeriodsDetailsRequest
from app import jobs
from app.modules.finops.azure.models import DownloadCostDetailsEAAccountRequest
from app.modules.finops.azure.scripts.Dwonload_cost_details_EA_account import (
    get_cost_details_ea_account,
)

# Real cost exports can be hundreds of thousands of rows; the on-screen table
# only needs a sample. The complete data is always available as a real file
# download, never trimmed.
PREVIEW_ROW_LIMIT = 500


class AzureService:
    @staticmethod
    def start_download_cost_details_ea_account(request: DownloadCostDetailsEAAccountRequest):
        def run(job_id):
            result = get_cost_details_ea_account(
                tenant_id=request.tenant_id,
                app_id=request.app_id,
                client_secret=request.client_secret,
                subscription_id=request.subscription_id,
                storage_account_name=request.storage_account_name,
                container_name=request.container_name,
                directory_path=request.directory_path,
                days_ago=request.days_ago,
                progress_callback=jobs.progress_callback_for(job_id),
            )

            file_bytes = result.pop("file_bytes", None)
            file_name = result.get("filename")

            preview = dict(result)
            full_row_count = len(preview.get("rows") or [])
            if full_row_count > PREVIEW_ROW_LIMIT:
                preview["rows"] = preview["rows"][:PREVIEW_ROW_LIMIT]
                preview["preview_row_limit"] = PREVIEW_ROW_LIMIT
            else:
                preview["preview_row_limit"] = None

            jobs.complete_job(
                job_id,
                result=preview,
                file_bytes=file_bytes,
                file_name=file_name,
                file_media_type="text/csv",
            )

        return jobs.run_in_background(run)


def stream_azure_ea_account_billing_periods_details(request: AzureEaAccountBillingPeriodsDetailsRequest):
    def run(progress_callback):
        return get_azure_billing_periods(
            tenant_id=request.tenant_id,
            application_id=request.application_id,
            application_secret=request.application_secret,
            azure_subscription_ids=request.azure_subscription_ids,
            progress_callback=progress_callback,
        )

    return execution.stream(run)
