from typing import Optional

from pydantic import BaseModel


class DecryptAzureSecretRequest(BaseModel):
    # The encrypted credentials.application_secret from the selected cloud
    # account — the only value actually processed.
    application_secret: str
    # Read-only details of the same account, echoed back in the result so the
    # panel shows (and "Apply" fills in) everything from one response.
    cloud_account_name: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    application_id: Optional[str] = None
    subscription_id: Optional[str] = None
    subscription_name: Optional[str] = None
    account_type: Optional[str] = None
