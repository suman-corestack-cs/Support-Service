import os
from pathlib import Path

from dotenv import load_dotenv

# Same .env as sts_config.py/mongo_config.py — resolved relative to this
# file so it works regardless of the process's current working directory.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def get_secret_decrypt_seed():
    """The seed CoreStack uses to derive the AES key that encrypts stored
    cloud-account secrets (e.g. service_account_details.credentials.
    application_secret) — used by the "Decrypt Secret Key" companion action
    (see app/modules/core/azure/scripts/Decrypt_azure_application_secret.py).
    Kept in .env rather than in source since anyone holding it can decrypt
    every stored secret."""
    return os.getenv("CORESTACK_SECRET_DECRYPT_SEED", "")
