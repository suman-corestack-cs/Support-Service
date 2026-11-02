from app import execution
from app.modules.secops.multicloud.models import BulkComplianceStandardsExecutionRequest
from app.modules.secops.multicloud.scripts.BulkComplianceStandardsExecution import (
    bulk_compliance_standards_execution,
)


class MulticloudService:
    @staticmethod
    def stream_bulk_compliance_standards_execution(request: BulkComplianceStandardsExecutionRequest):
        def run(progress_callback):
            return bulk_compliance_standards_execution(
                base_url=request.base_url,
                auth_token=request.auth_token,
                target_compliances=request.target_compliances,
                progress_callback=progress_callback,
            )

        return execution.stream(run)
