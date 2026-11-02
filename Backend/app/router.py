from fastapi import APIRouter

from app.modules.core.aws.routes import router as core_aws_router
from app.modules.core.azure.routes import router as core_azure_router
from app.modules.core.multicloud.routes import router as core_multicloud_router
from app.modules.finops.aws.routes import router as finops_aws_router
from app.modules.finops.azure.routes import router as finops_azure_router
from app.modules.secops.multicloud.routes import router as secops_multicloud_router
from app.modules.settings.routes import router as settings_router
from app.config_routes import router as config_router
from app.mongo_routes import router as mongo_router
from app.scripts_routes import router as scripts_router
from app.add_script.routes import router as add_script_router

router = APIRouter()

router.include_router(scripts_router)
router.include_router(mongo_router)
router.include_router(config_router)
router.include_router(add_script_router)
router.include_router(core_aws_router)
router.include_router(core_azure_router)
router.include_router(core_multicloud_router)
router.include_router(finops_aws_router)
router.include_router(finops_azure_router)
router.include_router(secops_multicloud_router)
router.include_router(settings_router)
