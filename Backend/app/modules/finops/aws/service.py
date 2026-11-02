from app.modules.finops.aws.scripts.S3_Buket_Details import get_s3_bucket_details
from app.modules.finops.aws.models import S3BuketDetailsRequest
from app import execution
from app.modules.finops.aws.models import ReservationSavingsPlansReportRequest
from app.modules.finops.aws.scripts.GetReservationSavingPlans import (
    get_reservation_and_savings_plans_report,
)


class AwsService:
    @staticmethod
    def stream_get_reservation_savings_plans_report(request: ReservationSavingsPlansReportRequest):
        def run(progress_callback):
            return get_reservation_and_savings_plans_report(
                access_key=request.access_key,
                secret_key=request.secret_key,
                session_token=request.session_token,
                region_names=request.region_names,
                service_types=request.service_types,
                resource_types=request.resource_types,
                term_in_years=request.term_in_years,
                payment_options=request.payment_options,
                granularity=request.granularity,
                start_date=request.start_date,
                end_date=request.end_date,
                progress_callback=progress_callback,
            )

        return execution.stream(run)


def stream_s3_buket_details(request: S3BuketDetailsRequest):
    def run(progress_callback):
        return get_s3_bucket_details(
            access_key=request.access_key,
            secret_key=request.secret_key,
            session_token=request.session_token,
            bucket_name=request.bucket_name,
            start_date=request.start_date,
            end_date=request.end_date,
        )

    return execution.stream(run)

