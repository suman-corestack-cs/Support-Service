from typing import Optional, List
from pydantic import BaseModel


class DownloadCostDetailsEAAccountRequest(BaseModel):
    tenant_id: str
    app_id: str
    client_secret: str
    subscription_id: str
    storage_account_name: str
    container_name: str
    directory_path: str
    days_ago: int = 0


class AzureEaAccountBillingPeriodsDetailsRequest(BaseModel):
    tenant_id: str
    application_id: str
    application_secret: str
    azure_subscription_ids: Optional[List[str]] = None
