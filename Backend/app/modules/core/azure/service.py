from datetime import datetime, timezone

from app import execution
from app.modules.core.azure.models import DecryptAzureSecretRequest
from app.modules.core.azure.scripts.Decrypt_azure_application_secret import decrypt_application_secret
from app.secret_decrypt_config import get_secret_decrypt_seed


class AzureService:
    @staticmethod
    def stream_decrypt_azure_application_secret(request: DecryptAzureSecretRequest):
        def run(progress_callback):
            result = decrypt_application_secret(request.application_secret, get_secret_decrypt_seed())
            if "error" in result:
                return result
            return {
                "cloud_account_name": request.cloud_account_name,
                "tenant_id": request.azure_tenant_id,
                "application_id": request.application_id,
                "application_secret": result["application_secret"],
                "subscription_id": request.subscription_id,
                "subscription_name": request.subscription_name,
                "type": request.account_type,
                "decrypted_at": datetime.now(timezone.utc).isoformat(),
            }

        return execution.stream(run)
