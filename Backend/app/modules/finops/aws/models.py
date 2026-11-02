from typing import List, Optional

from pydantic import BaseModel


class ReservationSavingsPlansReportRequest(BaseModel):
    access_key: str
    secret_key: str
    session_token: str
    region_names: List[str]
    service_types: Optional[List[str]] = None
    resource_types: Optional[List[str]] = None
    term_in_years: str = "ONE_YEAR"
    payment_options: Optional[List[str]] = None
    granularity: str = "MONTHLY"
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class S3BuketDetailsRequest(BaseModel):
    access_key: str
    secret_key: str
    session_token: str
    bucket_name: str
    start_date: str
    end_date: str

