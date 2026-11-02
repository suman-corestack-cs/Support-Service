import os
from pathlib import Path

from dotenv import load_dotenv

# Same .env as mongo_config.py — load_dotenv() is idempotent (safe to call
# again) and, like there, resolved relative to this file so it works
# regardless of the process's current working directory.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# Region key -> the .env variable holding that region's CoreStack API base URL.
REGION_API_URL_ENV_VARS = {
    "us": "API_US_URL",
    "msprod": "API_MSPROD_URL",
    "vlm": "API_VLM_URL",
    "eu": "API_EU_URL",
    "in": "API_IN_URL",
    "mea": "API_MEA_URL",
    "us3": "API_US3_URL",
    "useast": "API_USEAST_URL",
}


def get_region_api_urls():
    """Returns {region: api_url} for every region that has one configured."""
    urls = {}
    for region, env_var in REGION_API_URL_ENV_VARS.items():
        value = os.getenv(env_var)
        if value:
            urls[region] = value.strip()
    return urls
