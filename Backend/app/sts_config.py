import os
from pathlib import Path

from dotenv import load_dotenv

# Same .env as mongo_config.py/region_config.py — load_dotenv() is idempotent
# and resolved relative to this file so it works regardless of the process's
# current working directory.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)


def get_sts_credentials():
    """The fixed IAM user credentials used to call sts.assume_role for the
    "Generate Access & Secret Key" companion action (see
    app/modules/core/aws/scripts/Generate_access_key_and_secret_key.py) —
    these don't vary per request, they're the one IAM user CoreStack support
    uses to assume customer roles, configured once here rather than typed in
    on every use."""
    return {
        "access_key_id": os.getenv("STS_AWS_ACCESS_KEY_ID", ""),
        "secret_access_key": os.getenv("STS_AWS_SECRET_ACCESS_KEY", ""),
        "region_name": os.getenv("STS_AWS_REGION", "us-east-1"),
    }
