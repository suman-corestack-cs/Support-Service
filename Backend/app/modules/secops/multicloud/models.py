from typing import List

from pydantic import BaseModel


class BulkComplianceStandardsExecutionRequest(BaseModel):
    base_url: str
    auth_token: str
    target_compliances: List[str]
