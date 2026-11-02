from fastapi import APIRouter

from app.region_config import get_region_api_urls
from app.sts_config import get_sts_credentials

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("/region-api-urls")
def region_api_urls():
    """{region: api_url} for every configured region — not secret, just the
    base URLs, so this is a plain response (no streaming/job wrapper needed)."""
    return get_region_api_urls()


@router.get("/sts-credentials")
def sts_credentials():
    """The fixed IAM user credentials used by the "Generate Access & Secret
    Key" companion action. Unlike region-api-urls this genuinely is a
    secret — it's exposed here, read-only, only so the UI can show what's
    configured on demand instead of asking for it on every use. This
    endpoint carries no access control of its own; it inherits whatever
    fronts this API as a whole (currently none — see app/main.py)."""
    return get_sts_credentials()
