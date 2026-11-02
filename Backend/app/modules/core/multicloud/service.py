from app import execution
from app.modules.core.multicloud.models import BulkSyncStatusRequest
from app.modules.core.multicloud.scripts.BulkSyncStatus import bulk_sync_status


class MulticloudService:
    @staticmethod
    def stream_bulk_sync_status(request: BulkSyncStatusRequest):
        def run(progress_callback):
            return bulk_sync_status(
                service_account_ids=request.service_account_ids,
                base_url=request.base_url,
                auth_token=request.auth_token,
                total_records_processed=request.total_records_processed,
                request_delay_seconds=request.request_delay_seconds,
                progress_callback=progress_callback,
            )

        return execution.stream(run)
