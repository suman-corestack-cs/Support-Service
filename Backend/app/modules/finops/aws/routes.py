from app.modules.finops.aws.service import stream_s3_buket_details
from app.modules.finops.aws.models import S3BuketDetailsRequest
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.modules.finops.aws.models import ReservationSavingsPlansReportRequest
from app.modules.finops.aws.service import AwsService

router = APIRouter(prefix="/finops/aws", tags=["Finops - Aws"])


@router.post("/reservation-savings-plans-report")
def get_reservation_savings_plans_report(request: ReservationSavingsPlansReportRequest):
    generator = AwsService.stream_get_reservation_savings_plans_report(request)
    return StreamingResponse(generator, media_type="application/x-ndjson")


@router.post("/s3-buket-details")
def s3_buket_details(request: S3BuketDetailsRequest):
    return StreamingResponse(stream_s3_buket_details(request), media_type="application/x-ndjson")

