import pandas as pd
import requests
import time


def create_tenant(tenant_name, api_url, auth_token, master_account_id):
    headers = {
        "accept": "application/json",
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json"
    }

    payload = {
        "name": tenant_name,
        "account_id": master_account_id
    }

    # `api_url` is the per-region CoreStack API *base* URL (e.g.
    # "https://api.corestack.io/"), not the tenant-creation endpoint itself —
    # posting straight to the base URL 405s. The actual endpoint is
    # "<base>/tenants".
    endpoint = f"{api_url.rstrip('/')}/tenants"

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)

        if response.status_code in (200, 201):
            return {"tenant_name": tenant_name, "status": "success", "status_code": response.status_code}
        else:
            return {
                "tenant_name": tenant_name,
                "status": "failed",
                "status_code": response.status_code,
                "response": response.text,
            }

    except requests.exceptions.RequestException as e:
        return {"tenant_name": tenant_name, "status": "error", "error": str(e)}


def bulk_tenant_creation_using_excel(
    api_url,
    auth_token,
    master_account_id,
    request_delay_seconds=0.5,
    excel_file=None,
    tenant_name_column=None,
    tenant_names=None,
    progress_callback=None,
):
    results = []

    # Direct-entry mode: tenant names supplied straight from the UI, no
    # spreadsheet involved. Same per-tenant call and delay as file mode below.
    if tenant_names is not None:
        cleaned_names = [str(name).strip() for name in tenant_names if str(name).strip()]
        total_rows = len(cleaned_names)
        for row_number, tenant_name in enumerate(cleaned_names, start=1):
            results.append(create_tenant(tenant_name, api_url, auth_token, master_account_id))
            time.sleep(request_delay_seconds)
            if progress_callback:
                progress_callback(row_number, total_rows)
        return {"results": results}

    try:
        df = pd.read_excel(excel_file)

        if tenant_name_column not in df.columns:
            message = (
                f"[ERROR] Column '{tenant_name_column}' not found. "
                f"Available columns: {list(df.columns)}"
            )
            return {"error": message, "detected_columns": list(df.columns), "results": results}

        total_rows = len(df)
        for row_number, (index, tenant_name) in enumerate(enumerate(df[tenant_name_column], start=2), start=1):
            if pd.isna(tenant_name):
                results.append({"row": index, "status": "skipped"})
            else:
                tenant_name = str(tenant_name).strip()
                results.append(create_tenant(tenant_name, api_url, auth_token, master_account_id))
                time.sleep(request_delay_seconds)

            if progress_callback:
                progress_callback(row_number, total_rows)

    except FileNotFoundError:
        message = "[ERROR] Excel file not found."
        return {"error": message, "results": results}
    except Exception as e:
        message = f"[ERROR] Unexpected error: {e}"
        return {"error": message, "results": results}

    return {"results": results}
