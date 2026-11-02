import pathlib

_APP_DIR = pathlib.Path(__file__).resolve().parent

# Explicit allowlist: script id -> file path. Deliberately not derived from
# user input (e.g. a module/file query param), so this can never be used to
# read an arbitrary file off the server.
SCRIPT_SOURCES = {
    "core-aws-bulk-tenant-creation": _APP_DIR / "modules/core/aws/scripts/Bulck_tenant_creations_using_excel.py",
    "core-aws-role-permissions": _APP_DIR / "modules/core/aws/scripts/Get_role_permission.py",
    "core-multicloud-bulk-sync-status": _APP_DIR / "modules/core/multicloud/scripts/BulkSyncStatus.py",
    "finops-aws-reservation-savings-plans-report": _APP_DIR / "modules/finops/aws/scripts/GetReservationSavingPlans.py",
    "finops-azure-download-cost-details-ea-account": _APP_DIR / "modules/finops/azure/scripts/Dwonload_cost_details_EA_account.py",
    "secops-multicloud-bulk-compliance-standards-execution": _APP_DIR / "modules/secops/multicloud/scripts/BulkComplianceStandardsExecution.py",
    "settings-create-user-group": _APP_DIR / "modules/settings/scripts/Create_user_groups.py",
    "finops-aws-s3-buket-details": _APP_DIR / "modules/finops/aws/scripts/S3_Buket_Details.py",
    "core-aws-aws-config-rules-inventory-across-all-regions": _APP_DIR / "modules/core/aws/scripts/Aws_Config_Rules_Inventory_Across_All_Regions.py",
    "finops-azure-azure-ea-account-billing-periods-details": _APP_DIR / "modules/finops/azure/scripts/Azure_Ea_Account_Billing_Periods_Details.py",
}


def get_script_source_path(script_id):
    return SCRIPT_SOURCES.get(script_id)
