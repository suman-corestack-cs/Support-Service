# Service Support Project - Backend

FastAPI backend that exposes the support scripts as HTTP APIs.

## Setup

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Interactive docs: `http://localhost:8000/docs`
- Health check: `GET /health`

## Streamed execution

Every script can take a while to run (bulk loops, cloud API calls), so the `POST` endpoints below don't send back one big response at the end — they stream progress over the same connection as it happens, ending with exactly one final line once the script is fully done. There is only ever one HTTP request per run; nothing is polled.

The response body (`Content-Type: application/x-ndjson`) is newline-delimited JSON — read it line by line as it arrives:

```
{"status": "running", "processed": 1, "total": 5}
{"status": "running", "processed": 2, "total": 5}
...
{"status": "completed", "result": { ... }}
```

or, if the script raises:

```
{"status": "failed", "error": "..."}
```

- Zero or more `"running"` lines arrive while the script executes. `processed` / `total` are progress counters; `total` is `null` when the script has no discrete steps to count (e.g. a single API call) — treat that as indeterminate rather than a percentage.
- Exactly one final line ends the stream: `"completed"` with `result` (shape matches the "Job result" section documented per endpoint below), or `"failed"` with `error` (the exception message).

**One exception:** `/finops/azure/download-cost-details-ea-account` uses a different, *resumable* contract instead (see its section below) — the data it fetches can be large enough, and slow enough, that surviving a page refresh matters. The `POST` there returns a job id immediately instead of streaming, and the actual file is served by a separate `GET .../file` endpoint your browser can download natively.

## API Reference

Every endpoint below is a thin wrapper around a script in `app/modules/<module>/<cloud>/scripts/`. Hitting the endpoint starts that script as a job with the parameters you pass in the request.

---

### `POST /core/aws/bulk-tenant-creation`
Runs: `app/modules/core/aws/scripts/Bulck_tenant_creations_using_excel.py`

Creates a tenant for each given name via the given API — either read from an uploaded Excel file, or supplied directly as a comma-separated list. Exactly one of `excel_file`/`tenant_name_column` or `tenant_names` should be provided.

Request type: `multipart/form-data`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `api_url` | string | yes | Tenant-creation API endpoint to call for each row |
| `auth_token` | string | yes | Value sent as the `X-Auth-Token` header |
| `master_account_id` | string | yes | Master account ID sent with each tenant payload |
| `request_delay_seconds` | float | no (default `0.5`) | Delay between consecutive tenant-creation requests |
| `excel_file` | file | one of these two | Excel file containing the tenant names |
| `tenant_name_column` | string | with `excel_file` | Exact column name in the Excel file that holds tenant names |
| `tenant_names` | string | one of these two | Comma-separated tenant names to create directly, no file needed |

Progress: `total` = number of tenants (rows, or names in the comma-separated list), `processed` increments per tenant (including skipped rows in file mode).

Job result: `{"results": [{"tenant_name": ..., "status": "success" | "failed" | "error" | "skipped", ...}]}`

---

### `POST /core/aws/role-permissions`
Runs: `app/modules/core/aws/scripts/Get_role_permission.py` (`get_role_permissions`)

Lists the attached and inline IAM policies for a role.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `access_key` | string | yes | AWS access key ID |
| `secret_key` | string | yes | AWS secret access key |
| `session_token` | string | yes | AWS session token |
| `role_name` | string | yes | IAM role name to inspect |

Progress: `total` = number of attached + inline policies, `processed` increments per policy.

Job result: `{"attached_policies": [...], "inline_policies": [...]}`

---

### `POST /core/aws/generate-access-secret-key`
Runs: `app/modules/core/aws/scripts/Generate_access_key_and_secret_key.py`

Calls STS `assume_role` and returns temporary access/secret keys and a session token for the target role. Not its own script card in the UI — it's exposed as a side panel opened from both the "IAM Role Permissions" and "Reservation & Savings Plans Report" script pages (button below Expand All/Collapse All), since generating temporary credentials for a role is a companion action to those scripts rather than a standalone task.

The IAM user credentials used to call `assume_role` (`aws_access_key_id`/`aws_secret_access_key`/`region_name`) are **not** request parameters — they're fixed, configured once via `STS_AWS_ACCESS_KEY_ID`/`STS_AWS_SECRET_ACCESS_KEY`/`STS_AWS_REGION` in `Backend/.env` (see `app/sts_config.py`) and read server-side via `GET /config/sts-credentials`, which the UI's "Show AWS Creds" viewer calls for read-only display.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `role_arn` | string | yes | ARN of the role to assume — in the UI, resolved from the selected Cloud Account's `corestack_identity.service_account_details.credentials.assume_role_arn` (via Environment → Master Account → Tenant → Cloud Account dropdowns) |
| `role_session_name` | string | yes | Session name for the assumed-role session |
| `external_id` | string | no | External ID, if the role's trust policy requires one — resolved the same way from `credentials.assume_role_external_id` |

Progress: indeterminate (single API call, no `total`).

Job result: `{"access_key", "secret_key", "session_token", "expiration" (ISO 8601), "region", "role_arn", "role_name" (the role ARN's trailing segment), "assumed_role_user": {"arn", "assumed_role_id"}, "generated_at" (ISO 8601, UTC)}` on success; `{"error": "..."}` if `assume_role` failed. The UI renders `expiration` and `generated_at` in the browser's local time zone.

---

### `POST /core/multicloud/bulk-sync-status`
Runs: `app/modules/core/multicloud/scripts/BulkSyncStatus.py`

Posts a billing-sync status update for each service account ID.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `service_account_ids` | array[string] | yes | Service account IDs to update |
| `base_url` | string | yes | URL template with a `{}` placeholder for the service account ID, e.g. `https://api.example.com/accounts/{}/sync` |
| `auth_token` | string | yes | Value sent as the `X-Auth-Token` header |
| `total_records_processed` | int | no (default `0`) | Value sent in the `billing_info.total_records_processed` payload field |
| `request_delay_seconds` | float | no (default `1`) | Delay between consecutive requests |

Progress: `total` = number of service accounts, `processed` increments per account.

Job result: `[{"service_account_id": ..., "status_code": ..., "response": ...}]`

---

### `POST /finops/aws/reservation-savings-plans-report`
Runs: `app/modules/finops/aws/scripts/GetReservationSavingPlans.py`

Pulls current Reserved Instance and Savings Plan coverage, purchase recommendations, and utilization across EC2/RDS/ElastiCache/Redshift/OpenSearch. Each of the 7 report sections is its own independent AWS call wrapped in its own error handling — if one is denied (missing IAM permission, an explicit Deny, an SCP), the rest of the report still comes back; that call's failure is recorded in `diagnostics` instead of aborting the whole run.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `access_key` | string | yes | AWS access key ID |
| `secret_key` | string | yes | AWS secret access key |
| `session_token` | string | yes | AWS session token |
| `region_names` | array[string] | yes | AWS region(s) to query (multi-select in the UI). `describe_reserved_instances`/`describe_reserved_db_instances`/`describe_reserved_cache_nodes`/`describe_reserved_nodes`/`describe_reserved_instances` (opensearch) — feeding `ri_current_reservation` — are genuinely region-scoped by AWS, so that section runs once per region listed here and combines the results, each row tagged with the region it came from. Cost Explorer/Savings Plans data (every other section) isn't region-scoped this way — one shared client using the first listed region covers all of it regardless of how many regions were given. |
| `service_types` | array[string] | no (default: all of them) | Which report sections to run — any of `ri_current_reservation`, `ri_recommendations`, `ri_utilization`, `savings_plans_current`, `savings_plan_recommendations`, `savings_plan_utilization`, `savings_plan_coverage` (multi-select in the UI, labeled "Service Type"). Sections not selected are skipped entirely — not run and not returned — rather than just hidden. |
| `resource_types` | array[string] | no (default `["EC2", "RDS", "ELASTICACHE"]`) | Any of `EC2`, `RDS`, `ELASTICACHE`, `REDSHIFT`, `OPENSEARCH` — multi-select in the UI |
| `term_in_years` | string | no (default `"ONE_YEAR"`) | `ONE_YEAR` or `THREE_YEARS`, for RI/Savings Plan purchase recommendations |
| `payment_options` | array[string] | no (default `["NO_UPFRONT"]`) | Any of `NO_UPFRONT`, `PARTIAL_UPFRONT`, `ALL_UPFRONT` (multi-select in the UI). RI/Savings Plan recommendations are fetched once per option listed, each row tagged with which one produced it — AWS's recommendation APIs only accept one `PaymentOption` per call, so this loops rather than sending a list through in one request. |
| `granularity` | string | no (default `"MONTHLY"`) | Accepted but currently unused — see the `ri_utilization` note below |
| `start_date` | string | no | Start of the `YYYY-MM-DD` range for RI/Savings Plan utilization and coverage — with `end_date`, both default to the current month-to-date if either is omitted |
| `end_date` | string | no | End of that range — the UI won't let you pick a date after today |

The purchase-recommendation lookback window is fixed at `LookbackPeriodInDays: "THIRTY_DAYS"` server-side (`LOOKBACK_PERIOD_DAYS` in `GetReservationSavingPlans.py`) — not a request parameter. (Earlier versions of this script sent `LookbackPeriodInHours`, which isn't a real parameter of either recommendation API and always failed with a parameter-validation error — fixed.)

`savings_plans_current`'s `resource_types` filter previously matched against `productType`/`serviceCode` fields that don't exist on `DescribeSavingsPlans`' response — every plan was silently dropped whenever the filter was active (i.e. always, since `resource_types` defaults to a non-empty list), regardless of what plans actually existed. Fixed to match AWS's real `productTypes` array. `describe_savings_plans` is now also called with every valid `states` value passed explicitly, so a plan in any state (`payment-pending`/`payment-failed`/`active`/`retired`/`queued`/`queued-deleted`/`pending-return`/`returned`) is returned rather than relying on an undocumented default.

`savings_plan_recommendations` requests a different `SavingsPlansType` per resource now: `COMPUTE_SP` for EC2, `DATABASE_SP` for RDS/ElastiCache/Redshift/OpenSearch. It previously always requested `COMPUTE_SP`, which — unlike Reserved Instances — genuinely doesn't cover those non-EC2 services at all, so recommendations for them always came back empty regardless of actual usage.

`ri_current_reservation` now actually implements Redshift (`describe_reserved_nodes`) and OpenSearch (`describe_reserved_instances` on the `opensearch` client) lookups — both were previously unimplemented stubs that always contributed nothing regardless of what reservations existed, which was the main cause of this section appearing empty. Its 5 describe calls are genuinely region-scoped by AWS — unlike every other section here — which is why `region_names` loops per region for this section specifically. A resource type/region combination with zero reservations now contributes nothing at all (no placeholder row), rather than a `Note` row explaining the region-scoping — check the `region_names` list above if a resource type you expect to see is missing entirely.

`ri_utilization` (and the utilization merged into `ri_current_reservation`) is fetched via `GetReservationUtilization` with `GroupBy: [{"Type": "DIMENSION", "Key": "SUBSCRIPTION_ID"}]` — the only dimension that API supports grouping by — so it's broken down per individual reservation rather than aggregated across a resource type. AWS doesn't allow combining `GroupBy` with `Granularity`, so the `granularity` request parameter is accepted for backwards compatibility but no longer has any effect.

Progress: `total` = number of selected `service_types` (7 if omitted), `processed` increments as each section finishes.

Job result — only the selected `service_types` keys are present (plus `diagnostics`/`legend`, always). Every section is a **flat array of row objects** with plain-English column headers (curated and renamed from AWS's raw field names — not a pass-through — specifically so this is readable without AWS/Cost-Explorer background), so the UI renders each as its own table, in this order:
```
{
  "ri_current_reservation": [{"Resource Type", "Reservation SKU", "Region", "Payment Option", "Reservation Hours Used", "Utilization (%)", "Net Savings", "Purchased Hours", "Number of Reservations", "Reservation Hours Unused", "Start Date", "Expiry Date", "Status", "Reservation ID", "Currency", "Fixed Price", "Hourly Price"}, ...],
  "ri_recommendations": [{"Reservation Type", "Instance Family", "Reservation SKU", "Region", "Availability Zone", "Platform", "Database Engine", "Current Generation", "Number Of Reservations", "Look Back Period", "Term", "Payment Option", "Potential Savings", "Recommendation Id", "Scope", "Currency", "Avg Utilization %", "Estimated Monthly Savings %", "Estimated Monthly On-Demand Cost", "Upfront Cost", "Monthly Recurring Cost", "Break-Even (Months)"}, ...],
  "ri_utilization": [{"Resource Type", "Reservation ID", "Period Start", "Period End", "Utilization (%)", "Purchased Hours", "Reservation Hours Used", "Reservation Hours Unused", "Net Savings", "Realized Savings", "Unrealized Savings"}, ...],
  "savings_plans_current": [{"Savings Plan Name", "Savings Plan ID", "Account ID", "Scope", "Plan Type", "Payment Option", "Commitment/hour", "Term", "Status", "Start Date", "End Date", "Upfront Cost", "Utilization", "Currency", "Instance Family", "Product Types", "Region", "Recurring Payment"}, ...],
  "savings_plan_recommendations": [{"Recommendation ID", "Plan Type", "Scope", "Look Back Period", "Term", "Payment Option", "Commitment/hour", "Estimated Savings (%)", "Potential Savings (Month)", "Utilization", "Before Recommendation Purchase", "After Recommendation Purchase", "Currency", "Instance Family", "Region", "Resource Type", "Upfront Cost"}, ...],
  "savings_plan_utilization": [{"Savings Plan ID", "Savings Plan ARN", "Region", "Instance Family", "Total Commitment", "Used Commitment", "Unused Commitment", "Utilization (%)", "Net Savings", "On-Demand Cost Equivalent"}, ...],
  "savings_plan_coverage": [{"Resource Type", "Period Start", "Period End", "Coverage %", "Spend Covered by Savings Plans", "On-Demand Cost", "Total Cost"}, ...],
  "diagnostics": [{"action": ..., "status": ..., "deny_type": "IMPLICIT_DENY" | "EXPLICIT_DENY" | "N/A" | "UNKNOWN", "detail": ...}, ...],
  "legend": {"IMPLICIT_DENY": "...", "EXPLICIT_DENY": "..."}
}
```
A resource type whose call failed contributes one row with an `"Error"` key instead of data (and a matching entry in `diagnostics`). `ri_recommendations`/`savings_plan_recommendations` add a `"Note"` row when AWS has no recommendation for that resource/payment-option combination, and `ri_utilization` adds one when there's no utilization data for that resource type in the selected range — `ri_current_reservation` and `savings_plan_coverage` instead just contribute nothing for a resource/region with no data (no placeholder row), and `savings_plan_coverage`'s `DataUnavailableException` (no coverage data yet — not a permission problem) isn't logged as an error either.

`ri_recommendations`/`savings_plan_recommendations` flatten AWS's nested `InstanceDetails`/`SavingsPlansDetails` sub-object into their own top-level columns (`Instance Family`, `Reservation SKU`, `Region`, ...) rather than leaving it as one unreadable nested cell.

`ri_utilization` and `savings_plan_utilization` are both broken down **per individual reservation/Savings Plan** (identified by `Reservation ID`/`Savings Plan ID`), not aggregated across a whole resource type — `ri_utilization` does this via `GetReservationUtilization`'s `GroupBy: [{"Type": "DIMENSION", "Key": "SUBSCRIPTION_ID"}]` (the only dimension it supports grouping by; note this can't be combined with `Granularity`, so the `granularity` request parameter is accepted but currently unused), and `savings_plan_utilization` was already broken down this way per `SavingsPlanArn`. That same per-ID utilization data is also merged into the matching row of `ri_current_reservation`/`savings_plans_current` (by Reservation ID / Savings Plan ARN), which is why those two sections carry both static reservation/plan details *and* usage figures (`Reservation Hours Used`, `Utilization (%)`, `Net Savings`, ... / `Utilization`) together in one table.

A few columns come from data AWS doesn't actually expose at this layer and are always blank: `savings_plans_current.Scope` (no such field on `DescribeSavingsPlans`) — everything else is real, populated data.

---

### `POST /finops/azure/download-cost-details-ea-account`
Runs: `app/modules/finops/azure/scripts/Dwonload_cost_details_EA_account.py`

Finds the storage account's resource group, fetches its key, lists every blob in the given container/directory, and reads the most recent one that matches the `days_ago` threshold. Nothing is written to disk and no CSV file is created anywhere; the blob content is only ever held in memory (and briefly cached server-side, see below).

**This endpoint doesn't stream — it runs as a resumable background job**, because a real EA cost export can be large and slow enough to fetch that surviving a page refresh matters:

1. `POST` starts the fetch in a background thread and returns immediately:
   ```
   202 Accepted
   { "job_id": "3f9e..." }
   ```
   That thread keeps running to completion on the server regardless of what the client does afterward — closing the tab, losing the connection, or reloading the page does not stop it.
2. `GET /finops/azure/download-cost-details-ea-account/{job_id}/status` — poll this (from the same page load or a completely fresh one after a refresh) to get progress and, once finished, the result:
   ```
   {
     "job_id": "3f9e...",
     "status": "running" | "completed" | "failed",
     "processed": 683590,
     "total": 2000000,
     "result": { ... } | null,
     "error": "..." | null
   }
   ```
   `processed`/`total` are bytes fetched vs. the matched blob's total size (indeterminate until a matching blob is found). A `job_id` that no longer exists (server restarted, or pruned after an hour) returns `404`.
3. Once `status` is `"completed"`, `result` looks like:
   ```
   {
     "available_blobs": [{"name": ..., "path": ..., "last_modified": ..., "size_bytes": ...}, ...],
     "matched_blob": "<filename>" | null,
     "resource_group": "<resource group name>" | null,
     "filename": "<filename>" | null,
     "columns": ["col_a", "col_b", ...],
     "rows": [["value_a", "value_b", ...], ...],   // capped preview, see preview_row_limit
     "row_count": N,                                 // the TRUE total, uncapped
     "preview_row_limit": 500 | null,                 // set when rows was capped for display
     "download_url": "/finops/azure/download-cost-details-ea-account/{job_id}/file"
   }
   ```
   `rows` is capped at 500 entries purely for on-screen preview — a table isn't a reasonable way to browse hundreds of thousands of rows anyway. `row_count` always reflects the true total. `available_blobs` lists every blob found in the directory (not just the one selected). Each entry in `rows` is a plain array of values in `columns` order, not one object per row, to keep the preview payload small.
4. `GET /finops/azure/download-cost-details-ea-account/{job_id}/file` — serves the **complete, byte-identical** original CSV (not the capped preview) with `Content-Disposition: attachment`, so a browser hitting this URL (e.g. via a plain `<a href>` click) triggers a real, native download — independent of the page's JS state, and still valid after a refresh, until the job is pruned (completed/failed jobs are kept for about an hour).

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `tenant_id` | string | yes | Azure AD tenant ID |
| `app_id` | string | yes | Service principal (app) ID |
| `client_secret` | string | yes | Service principal client secret |
| `subscription_id` | string | yes | Azure subscription ID containing the storage account |
| `storage_account_name` | string | yes | Storage account to search |
| `container_name` | string | yes | Blob container name |
| `directory_path` | string | yes | Directory/prefix inside the container to search |
| `days_ago` | int | no (default `0`) | Selects the blob dated this many days before the most recent blob |

---

### `POST /secops/multicloud/bulk-compliance-standards-execution`
Runs: `app/modules/secops/multicloud/scripts/BulkComplianceStandardsExecution.py`

For every tenant, executes the matching compliance standards against every active cloud account.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_url` | string | yes | Base URL of the CoreStack API |
| `auth_token` | string | yes | Value sent as the `X-Auth-Token` header |
| `target_compliances` | array[string] | yes | Compliance standard names to execute (matched against `compliance_name`) |

Progress: `total` = number of tenants, `processed` increments per tenant (coarse-grained — a tenant may involve multiple account/URI executions).

Job result: `[{"tenant_id": ..., "executions": [{"cloud_account_id": ..., "compliance_uri": ..., "status": "success" | "failed", ...}]}]`

---

### `POST /settings/create-user-group`
Runs: `app/modules/settings/scripts/Create_user_groups.py`

Fetches all tenants under the master account, matches roles by name across those tenants, and creates a user group with the matched roles and given users.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `base_url` | string | yes | Base URL of the CoreStack API |
| `master_account_id` | string | yes | Master account ID to fetch tenants from |
| `auth_token` | string | yes | Value sent as the `X-Auth-Token` header |
| `user_ids` | array[string] | yes | User IDs to add to the group |
| `group_name` | string | yes | Name of the user group to create |
| `required_role_ids` | array[string] | yes | Role **names** to match and attach to the group (matched against each tenant's role list) |

Progress: `total` = number of tenants, `processed` increments per tenant while fetching roles.

Job result: `{"payload": {...}, "response": {...}, "tenant_roles": [...]}` on success; `{"error": "...", "tenant_roles": [...]}` if no tenant had a matching role; or `{"payload": {...}, "error": {...}, "tenant_roles": [...]}` if group creation failed. `tenant_roles` is the full per-tenant role listing fetched along the way. Nothing is written to disk — everything the script sees comes back in the response.

---

### `POST /mongo/query`
Config: `app/mongo_config.py` · Route: `app/mongo_routes.py`

Runs a **read-only** MongoDB query against one of the CoreStack regional databases and returns the matching documents. This isn't a wrapper around a customer script like the endpoints above — it's a direct, generic query tool over the connections configured in `Backend/.env`.

`app/mongo_config.py` loads `Backend/.env` (via `python-dotenv`, which resolves the `${US_PASSWORD}`-style references inside each `MONGO_*_URI`) and maps a `region` key to the matching URI env var:

| region | env var |
|---|---|
| `us` | `MONGO_US_URI` |
| `msprod` | `MONGO_MSPROD_URI` |
| `vlm` | `MONGO_VLM_URI` |
| `eu` | `MONGO_EU_URI` |
| `in` | `MONGO_IN_URI` |
| `mea` | `MONGO_MEA_URI` |
| `us3` | `MONGO_US3_URI` |
| `useast` | `MONGO_USEAST_URI` |

One `MongoClient` is created and cached per region on first use (safe to share across requests — pymongo manages its own connection pool).

**Read-only by design:** `filter`/`pipeline` are scanned recursively and rejected with a clear error if they contain `$where`, `$function`, or `$accumulator` (all execute arbitrary server-side JavaScript) or `$out`/`$merge` (both write data). There is no way to mutate data or run custom code through this endpoint.

Request type: `application/json`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `region` | string | yes | One of the region keys above |
| `database` | string | no | Defaults to the database named in the URI (the auth database, typically `admin`) |
| `collection` | string | yes | Collection name |
| `operation` | string | no (default `"find"`) | `find`, `aggregate`, or `count` |
| `filter` | object | no | Query filter, used by `find`/`count` |
| `projection` | object | no | Field projection, used by `find` |
| `sort` | array of `[field, 1\|-1]` pairs | no | Used by `find` |
| `limit` | int | no (default `100`, capped at `1000`) | Max documents returned by `find`/`aggregate` (not applied to `count`) |
| `pipeline` | array of objects | no | Aggregation pipeline, used by `aggregate` |

Job result: `{"documents": [...], "count": N}` for `find`/`aggregate` (documents capped at `limit`), or `{"count": N}` for `count` (the true total, uncapped). ObjectId and datetime fields come back as MongoDB Extended JSON (`{"$oid": "..."}`, `{"$date": "..."}`).

`filter`/`pipeline` accept MongoDB Extended JSON going *in* too — e.g. `{"tenant_id": {"$oid": "<hex>"}}` to match an ObjectId field — hydrated into real BSON types server-side before the query/pipeline runs (and only after the read-only scan above, so this can't be used to smuggle in a forbidden operator).

Verified against a disposable local MongoDB instance during development — never against the real regional databases in `.env`.

---

### `GET /config/region-api-urls`
Config: `app/region_config.py` · Route: `app/config_routes.py`

Returns the per-region CoreStack API base URL, read from `Backend/.env` (`API_US_URL`, `API_MSPROD_URL`, etc. — same region keys as `/mongo/query`). Not secret (just base URLs), so this is a plain, unstreamed `GET` — the UI uses it to auto-select an "API URL" field once an Environment/region is chosen elsewhere in a form.

Response: `{"us": "https://api.corestack.io/", "msprod": "https://api-msprod.corestack.io/", ...}` — only regions with a configured URL are included.

---

### `GET /config/sts-credentials`
Config: `app/sts_config.py` · Route: `app/config_routes.py`

Returns the fixed IAM user credentials used by `POST /core/aws/generate-access-secret-key` to call `sts.assume_role` (`STS_AWS_ACCESS_KEY_ID`/`STS_AWS_SECRET_ACCESS_KEY`/`STS_AWS_REGION` in `Backend/.env`). Unlike `/config/region-api-urls` this **is** a real secret — it exists only so the "Generate Access & Secret Key" panel's "Show AWS Creds" viewer can display what's configured, read-only, instead of asking for it on every use. It carries no access control beyond whatever fronts this API as a whole (currently none).

Response: `{"access_key_id": "...", "secret_access_key": "...", "region_name": "us-east-1"}`.

---

### `POST /admin/add-script`
Route: `app/add_script/routes.py` · Analysis: `app/add_script/code_generation.py` · Code generation: `app/add_script/file_writer.py`

Powers the "Add Script" wizard (bottom of the sidebar in the UI). Given a raw, uploaded `.py` script plus a sample of its output, this calls the Anthropic API (`ANTHROPIC_API_KEY` in `Backend/.env`) to analyze it and convert it into the same shape as every hand-built script above (a side-effect-free function taking explicit parameters and returning a JSON-serializable result), then **writes and wires it into this running codebase itself** — appending to `models.py`/`service.py`/`routes.py` for the target module, registering the router in `app/router.py` if that bundle/cloud combo has never been used before, adding an entry to `app/script_sources.py` (for "View Script"), and adding the corresponding entry to `Frontend/src/scriptsData.js` so it shows up as a script card.

This is a synchronous, plain JSON response (not the streamed contract above) — it's a one-shot admin action, not a script run, though the Claude call inside it can take up to a minute or so for a large script.

**Every file edit this makes is append-only** — a new file, or an addition just before a known closing brace/bracket/array-end — never a modification to code already there. Existing scripts and routes are never touched.

**Important: both the backend and frontend need to be restarted after a successful call, before the new script actually shows up and runs.** The new route is only wired into the running FastAPI app's routing table at import time — the backend process must be restarted (`uvicorn app.main:app --reload` picks this up automatically if it's already running with `--reload`; otherwise restart it manually) before the new script's endpoint actually responds. The response's `router_newly_registered` field tells you whether a new router import had to be added to `app/router.py` at all (`false` means this bundle/cloud combo already had other scripts registered, so a restart is the only prerequisite either way). Separately, `Frontend/src/scriptsData.js` just changed on disk — restart the frontend dev server (or reload the page if Vite's dev server is already running and picks up the change via HMR) so the new script card actually appears.

Request type: `multipart/form-data`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `script_name` | string | yes | Human-readable name, e.g. "Bulk Disable Billing" — drives the generated function/class/file names and the UI card title |
| `bundle` | string | yes | One of `core`, `finops`, `secops`, `cloudops`, `reports`, `settings` |
| `cloud` | string | required unless `bundle` is `settings` | One of `aws`, `azure`, `gcp`, `oci`, `multicloud` — `settings` has no cloud subfolder, so this must be omitted/blank for it |
| `description` | string | no | Free-text description of what the script does — may also suggest how its output should be displayed (e.g. "show as a table sorted by size"), which Claude uses as guidance when shaping the returned data, not just as background context |
| `script_files` | file[] | yes, at least one | The script's own source (`.py` only — anything else is rejected with `400` before any analysis happens). More than one file is supported for a script split across modules |
| `output_files` | file[] | no | A real sample of what the script produces — `.xlsx`/`.xls`/`.xlsm` (summarized via `openpyxl`; a genuine legacy `.xls` that doesn't parse falls back to a raw-text preview rather than failing), `.csv`/`.tsv`/`.txt` (read as plain text), or `.pdf` (read natively by Claude), rejected with `400` for any other extension. Used purely as analysis context, never stored — when given, this is Claude's ground truth for what fields/values actually exist |

Response (`200`):
```
{
  "script_id": "reports-gcp-bulk-disable-billing",
  "endpoint": "/reports/gcp/bulk-disable-billing",
  "script_file": "app/modules/reports/gcp/scripts/Bulk_Disable_Billing.py",
  "router_newly_registered": true,
  "summary": "Reads a CSV of project IDs and disables billing for each one."
}
```

Errors: `400` for anything the caller controls being wrong (a non-`.py` script upload, an invalid `bundle`/`cloud`, a script name that collides with an id already registered); `502` if the Anthropic API call itself fails or Claude's response doesn't parse into the expected shape (nothing is written to disk in that case — analysis happens entirely before any file is touched).

---

### `DELETE /admin/scripts/{script_id}`
Route: `app/add_script/routes.py` · Removal: `app/add_script/delete_script.py`

Reverses `POST /admin/add-script` for one script — powers the delete icon next to "Collapse All" on a script's page, which gates this behind a "type delete to confirm" dialog before calling it. Always removes the script's `scriptsData.js` entry, its `script_sources.py` entry, and its `scripts/*.py` file; best-effort removes its generated Pydantic model (if it took a JSON body), service function, and route — "best-effort" meaning each of those three is only removed if a name derived the same deterministic way the generator built it is actually found, so this is safe to call even on a hand-written script that doesn't follow those conventions (it just won't have anything to clean up there). `app/router.py`'s router registration is never touched, on either add or delete — an included router with no routes left in it is harmless, and there's no reliable way to know it's safe to remove without risking another script that shares the same bundle/cloud.

**Every file this endpoint is about to change is copied first** into `Backend/.add_script_backups/<timestamp>_<script_id>/` (gitignored) — cheap insurance given this is the one place in the whole feature that edits the middle of a file instead of just appending to it.

Same restart requirement as adding a script: the route doesn't actually disappear from the running backend, and the card doesn't disappear from the running frontend, until both are restarted.

Response (`200`):
```
{
  "script_id": "reports-gcp-bulk-disable-billing",
  "title": "Bulk Disable Billing",
  "removed": {
    "script_file": true,
    "pydantic_model": false,
    "service_function": true,
    "route": true
  }
}
```

Errors: `404` if no script with that id is registered in `scriptsData.js`.
