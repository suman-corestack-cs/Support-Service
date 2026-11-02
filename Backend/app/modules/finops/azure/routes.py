from fastapi.responses import StreamingResponse
from app.modules.finops.azure.service import stream_azure_ea_account_billing_periods_details
from app.modules.finops.azure.models import AzureEaAccountBillingPeriodsDetailsRequest
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app import jobs
from app.modules.finops.azure.models import DownloadCostDetailsEAAccountRequest
from app.modules.finops.azure.service import AzureService

router = APIRouter(prefix="/finops/azure", tags=["Finops - Azure"])

_PREFIX = "/finops/azure"  # the router's own prefix, needed to build absolute URLs in responses
_BASE = "/download-cost-details-ea-account"


@router.post(_BASE, status_code=status.HTTP_202_ACCEPTED)
def download_cost_details_ea_account(request: DownloadCostDetailsEAAccountRequest):
    # Runs in a background thread that keeps going to completion regardless of
    # this connection — the job id lets the UI reconnect after a refresh
    # instead of losing an in-progress (or already-finished) fetch.
    job_id = AzureService.start_download_cost_details_ea_account(request)
    return {"job_id": job_id}


@router.get(_BASE + "/{job_id}/status")
def download_cost_details_ea_account_status(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = job["result"]
    if job["status"] == "completed" and result is not None:
        result = {**result, "download_url": f"{_PREFIX}{_BASE}/{job_id}/file"}

    return {
        "job_id": job_id,
        "status": job["status"],
        "processed": job["processed"],
        "total": job["total"],
        "result": result,
        "error": job["error"],
    }


@router.get(_BASE + "/{job_id}/file")
def download_cost_details_ea_account_file(job_id: str):
    job = jobs.get_job(job_id)
    if not job or job["status"] != "completed" or not job["file_bytes"]:
        raise HTTPException(status_code=404, detail="File not ready or not found")

    filename = job["file_name"] or "export.csv"
    return Response(
        content=job["file_bytes"],
        media_type=job["file_media_type"] or "text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/azure-ea-account-billing-periods-details")
def azure_ea_account_billing_periods_details(request: AzureEaAccountBillingPeriodsDetailsRequest):
    return StreamingResponse(stream_azure_ea_account_billing_periods_details(request), media_type="application/x-ndjson")
