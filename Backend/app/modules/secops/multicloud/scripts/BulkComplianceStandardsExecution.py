import requests


class CorestackClient:
    def __init__(self, base_url, headers):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(headers)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json()

    # Return multiple tenant IDs
    def get_tenant_ids_by_name(self):
        data = self._request("GET", "/tenants")
        tenants = data.get("tenants", [])

        return [
            tenant.get("tenant_id")
            for tenant in tenants
        ]

    # Return only cloud account IDs
    def get_cloud_account_ids(self, tenant_id):
        payload = {
            "filters": {
                "tenant_ids": [tenant_id],
                "statuses": ["active"],
                "native_details": [
                {
                    "type": "ServiceAccountNativeDetailsBaseForAws"
                },
                {
                    "type": "ServiceAccountNativeDetailsForCostCenterAws"
                },
                {
                    "type": "ServiceAccountNativeDetailsBaseForCostCenterDimension"
                },
                {
                    "type": "ServiceAccountNativeDetailsForAwsEksCluster"
                }
                ]
            }
        }

        data = self._request("POST", "/v2/service_account/list", json=payload)
        results = data.get("results", [])

        cloud_account_ids = []

        for acct in results:
            if isinstance(acct, dict):
                acct_id = acct.get("id")
                if acct_id:
                    cloud_account_ids.append(acct_id)

            elif isinstance(acct, str):
                cloud_account_ids.append(acct)

        return cloud_account_ids

    def get_compliance_uris(self, tenant_id, target_compliances):
        params = {
            "type": "marketplace",
            "valid_service_type": "AWS"
        }

        data = self._request(
            "GET",
            f"/compliance/{tenant_id}/standards",
            params=params
        )

        records = data.get("data", data if isinstance(data, list) else [])

        return [
            item.get("compliance_uri")
            for item in records
            if item.get("compliance_name", "").strip() in target_compliances
        ]

    # Execute compliance for ONE cloud account and ONE URI
    def execute_compliance_on_demand(self, tenant_id, cloud_account_id, compliance_uri):
        if not cloud_account_id or not compliance_uri:
            return {"error": "Missing cloud account ID or compliance URI."}

        payload = {
            "cloud_accounts": [cloud_account_id],  # single account as list
            "compliance_uri": compliance_uri
        }

        endpoint = f"/compliance/{tenant_id}/control_mapping/on_demand_execute_standard"

        return self._request("POST", endpoint, json=payload)


def bulk_compliance_standards_execution(base_url, auth_token, target_compliances, progress_callback=None):
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "X-Auth-Token": auth_token
    }

    client = CorestackClient(base_url, headers)
    target_compliances = set(target_compliances)

    tenant_ids = client.get_tenant_ids_by_name()
    total_tenants = len(tenant_ids)

    summary = []

    for tenant_index, tenant_id in enumerate(tenant_ids, start=1):
        tenant_summary = {"tenant_id": tenant_id, "executions": []}

        cloud_account_ids = client.get_cloud_account_ids(tenant_id)
        if not cloud_account_ids:
            tenant_summary["message"] = "No cloud accounts found. Skipping tenant."
            summary.append(tenant_summary)
            if progress_callback:
                progress_callback(tenant_index, total_tenants)
            continue

        compliance_uris = client.get_compliance_uris(tenant_id, target_compliances)
        if not compliance_uris:
            tenant_summary["message"] = "No matching compliance URIs found. Skipping tenant."
            summary.append(tenant_summary)
            if progress_callback:
                progress_callback(tenant_index, total_tenants)
            continue

        # Execute EACH URI for EACH cloud account
        for account_id in cloud_account_ids:
            for uri in compliance_uris:
                try:
                    response = client.execute_compliance_on_demand(
                        tenant_id,
                        account_id,
                        uri
                    )
                    tenant_summary["executions"].append({
                        "cloud_account_id": account_id,
                        "compliance_uri": uri,
                        "status": "success",
                        "response": response,
                    })
                except Exception as e:
                    tenant_summary["executions"].append({
                        "cloud_account_id": account_id,
                        "compliance_uri": uri,
                        "status": "failed",
                        "error": str(e),
                    })

        summary.append(tenant_summary)
        if progress_callback:
            progress_callback(tenant_index, total_tenants)

    return summary
