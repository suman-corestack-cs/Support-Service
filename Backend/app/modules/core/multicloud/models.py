from typing import List

from pydantic import BaseModel


class BulkSyncStatusRequest(BaseModel):
    service_account_ids: List[str]
    base_url: str
    auth_token: str
    total_records_processed: int = 0
    request_delay_seconds: float = 1
