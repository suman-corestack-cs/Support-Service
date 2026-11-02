#pip install azure-identity azure-mgmt-storage azure-mgmt-resource azure-storage-blob
from azure.identity import ClientSecretCredential
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.resource.resources import ResourceManagementClient
from azure.storage.blob import BlobServiceClient
from datetime import timedelta
import csv
import io


def find_resource_group(resource_client, storage_client, storage_account_name):
    for resource_group in resource_client.resource_groups.list():
        try:
            storage_client.storage_accounts.get_properties(resource_group.name, storage_account_name)
            return resource_group.name
        except Exception:
            continue

    return None


def saKey(storage_client, resource_group_name, storage_account_name):
    if resource_group_name:
        storage_keys = storage_client.storage_accounts.list_keys(resource_group_name, storage_account_name)
        first_key = storage_keys.as_dict()['keys'][0]['value']
        return first_key


def get_latest_cost_export(container_client, directory_path, days_ago, progress_callback=None):
    blobs = list(container_client.list_blobs(name_starts_with=directory_path))
    if not blobs:
        return {"available_blobs": [], "matched_blob": None, "filename": None, "columns": [], "rows": [], "row_count": 0}

    sorted_blobs = sorted(blobs, key=lambda b: b['last_modified'])

    available_blobs = []
    for blob in sorted_blobs:
        size_bytes = blob['size']
        available_blobs.append({
            "name": blob.name.split('/')[-1],
            "path": blob.name,
            "last_modified": blob['last_modified'].isoformat(),
            "size_bytes": size_bytes,
        })

    most_recent_blob = max(blobs, key=lambda blob: blob['last_modified'])
    most_recent_date = most_recent_blob['last_modified'].date()
    threshold_date = most_recent_date - timedelta(days=days_ago)

    old_blobs = [
        blob for blob in blobs if blob['last_modified'].date() == threshold_date
    ]
    if old_blobs:
        latest_old_blob = max(old_blobs, key=lambda blob: blob['last_modified'])
        blob_client = container_client.get_blob_client(latest_old_blob.name)

        total_size = latest_old_blob['size']
        fetched = 0
        stream = blob_client.download_blob(max_concurrency=8)
        buffer = io.BytesIO()
        for chunk in stream.chunks():
            buffer.write(chunk)
            fetched += len(chunk)
            if progress_callback:
                progress_callback(fetched, total_size)

        filename = latest_old_blob.name.split('/')[-1]

        buffer.seek(0)
        text = buffer.getvalue().decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows_iter = iter(reader)
        columns = next(rows_iter, [])
        # Rows as plain value lists (not one dict with all column names per row) —
        # a full EA cost export can be hundreds of thousands of rows, and repeating
        # every column name in every row bloats the JSON response multiple times over.
        rows = list(rows_iter)

        return {
            "available_blobs": available_blobs,
            "matched_blob": filename,
            "filename": filename,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            # Exact original bytes, for serving a byte-identical file download —
            # separate from `rows`, which is a parsed copy for on-screen display.
            "file_bytes": buffer.getvalue(),
        }
    else:
        return {
            "available_blobs": available_blobs,
            "matched_blob": None,
            "filename": None,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "file_bytes": None,
        }


def get_cost_details_ea_account(
    tenant_id,
    app_id,
    client_secret,
    subscription_id,
    storage_account_name,
    container_name,
    directory_path,
    days_ago=0,
    progress_callback=None,
):
    credential = ClientSecretCredential(tenant_id, app_id, client_secret)
    resource_client = ResourceManagementClient(credential, subscription_id)
    storage_client = StorageManagementClient(credential, subscription_id)

    resource_group_name = find_resource_group(resource_client, storage_client, storage_account_name)

    saKeyValue = saKey(storage_client, resource_group_name, storage_account_name)
    blob_service_client = BlobServiceClient(account_url=f"https://{storage_account_name}.blob.core.windows.net", credential=saKeyValue)
    container_client = blob_service_client.get_container_client(container_name)

    result = get_latest_cost_export(container_client, directory_path, days_ago, progress_callback)
    result["resource_group"] = resource_group_name
    return result
