import requests
import time


def bulk_sync_status(service_account_ids, base_url, auth_token, total_records_processed=0, request_delay_seconds=1, progress_callback=None):
    headers = {
        "Content-Type": "application/json",
        "X-Auth-Token": auth_token
    }

    payload = {
        "billing_info": {
            "total_records_processed": total_records_processed
        }
    }

    results = []
    total = len(service_account_ids)

    # Loop through all service account IDs
    for index, service_account_id in enumerate(service_account_ids, start=1):
        url = base_url.format(service_account_id)

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30
            )

            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            results.append({
                "service_account_id": service_account_id,
                "status_code": response.status_code,
                "response": response_body,
            })

        except requests.exceptions.RequestException as e:
            results.append({"service_account_id": service_account_id, "error": str(e)})

        if progress_callback:
            progress_callback(index, total)

        # Optional delay between requests
        time.sleep(request_delay_seconds)

    return results
