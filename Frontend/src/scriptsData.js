import { API_BASE_URL, queryMongo } from "./api";

// CoreStack regional environments, matching Backend/app/mongo_config.py's
// MONGO_REGION_ENV_VARS keys.
export const ENVIRONMENTS = [
  { value: "us", label: "US" },
  { value: "msprod", label: "MSPROD" },
  { value: "vlm", label: "VLM" },
  { value: "eu", label: "EU" },
  { value: "in", label: "IN" },
  { value: "mea", label: "MEA" },
  { value: "us3", label: "US3" },
];

// Looks up the active master accounts for a given environment from
// corestack_identity.master_account, ascending by name — used to populate
// the Master Account dropdown once an environment is picked. The script
// needs the account's _id (not its name), so each option's value is the id
// while its label is the human-readable name.
async function loadMasterAccountNames(environment) {
  const result = await queryMongo({
    region: environment,
    database: "corestack_identity",
    collection: "master_account",
    operation: "find",
    filter: { status: "active" },
    projection: { name: 1 }, // _id comes back by default unless explicitly excluded
    sort: [["name", 1]],
    limit: 1000,
  });
  return (result.documents || [])
    .filter((doc) => doc.name && doc._id)
    .map((doc) => ({ value: doc._id.$oid ?? String(doc._id), label: doc.name }));
}

// Active tenants (projects) under a given master account, ascending by name
// — populates the Tenant dropdown once a Master Account is picked. `values`
// carries the whole form so this can reach the Environment picked upstream
// (its own immediate dependency is only the master account id).
async function loadTenantNames(masterAccountId, values) {
  const result = await queryMongo({
    region: values.environment,
    database: "corestack_identity",
    collection: "project",
    operation: "find",
    filter: { project_master_id: { $oid: masterAccountId }, status: "active" },
    projection: { name: 1 },
    sort: [["name", 1]],
  });
  return (result.documents || [])
    .filter((doc) => doc.name && doc._id)
    .map((doc) => ({ value: doc._id.$oid ?? String(doc._id), label: doc.name }));
}

// Active AWS cloud accounts under a given tenant, ascending by name —
// populates the Cloud Account dropdown once a Tenant is picked. Each option
// also carries the account's assume-role ARN/external ID (from
// `credentials`), since selecting a Cloud Account is really what supplies
// those two values for the "Generate Access & Secret Key" request.
async function loadCloudAccounts(tenantId, values) {
  const result = await queryMongo({
    region: values.environment,
    database: "heatstack",
    collection: "service_account_details",
    operation: "find",
    filter: {
      tenant_id: { $oid: tenantId },
      status: "active",
      "native_details.type": { $regex: "aws", $options: "i" },
    },
    projection: { name: 1, credentials: 1, native_details: 1 },
    sort: [["name", 1]],
  });
  return (result.documents || [])
    .filter((doc) => doc.name && doc._id && doc.credentials?.assume_role_arn)
    .map((doc) => ({
      value: doc._id.$oid ?? String(doc._id),
      label: doc.name,
      assumeRoleArn: doc.credentials.assume_role_arn,
      assumeRoleExternalId: doc.credentials.assume_role_external_id || null,
      assumeRoleMfaEnabled: doc.credentials.assume_role_mfa_enabled ?? null,
      accountRegions: doc.native_details?.regions || null,
      bucketNameOrUri: doc.native_details?.bucket_name_or_uri ?? null,
      accountType: doc.native_details?.type || null,
    }));
}

// Active Azure cloud accounts under a given tenant, ascending by name — same
// lookup as loadCloudAccounts but filtered to Azure service accounts. Each
// option carries the account's still-encrypted application secret plus the
// details shown alongside it once decrypted.
async function loadAzureCloudAccounts(tenantId, values) {
  const result = await queryMongo({
    region: values.environment,
    database: "heatstack",
    collection: "service_account_details",
    operation: "find",
    filter: {
      tenant_id: { $oid: tenantId },
      status: "active",
      "native_details.type": { $regex: "azure", $options: "i" },
    },
    projection: { name: 1, credentials: 1, native_details: 1 },
    sort: [["name", 1]],
  });
  return (result.documents || [])
    .filter((doc) => doc.name && doc._id && doc.credentials?.application_secret)
    .map((doc) => ({
      value: doc._id.$oid ?? String(doc._id),
      label: doc.name,
      encryptedSecret: doc.credentials.application_secret,
      azureTenantId: doc.credentials.tenant_id || null,
      applicationId: doc.credentials.application_id || null,
      subscriptionId: doc.native_details?.subscription_id || null,
      subscriptionName: doc.native_details?.subscription_name || null,
      accountType: doc.native_details?.type || null,
      storageAccount: doc.native_details?.storage_account ?? null,
      reportPath: doc.native_details?.report_path ?? null,
    }));
}

// Environment → Master Account → Tenant: the CoreStack account picker both
// companion panels start with, ending in a cloud-account dropdown loaded by
// `loadAccounts` (AWS or Azure accounts under the chosen tenant).
function cloudAccountPickerInputs({ loadAccounts, accountDescription }) {
  return [
    {
      name: "environment",
      label: "Environment",
      type: "select",
      required: true,
      description: "CoreStack region — drives the Master Account list",
      options: ENVIRONMENTS,
      excludeFromSubmit: true,
    },
    {
      name: "master_account_id",
      label: "Master Account",
      type: "dynamic-select",
      required: true,
      description: "Master account whose tenants to choose from",
      dependsOn: "environment",
      loadOptions: loadMasterAccountNames,
      searchable: true,
      excludeFromSubmit: true,
    },
    {
      name: "tenant_id",
      label: "Tenant",
      type: "dynamic-select",
      required: true,
      description: "Tenant (project) under the selected master account",
      dependsOn: "master_account_id",
      loadOptions: loadTenantNames,
      searchable: true,
      excludeFromSubmit: true,
    },
    {
      name: "cloud_account_id",
      label: "Cloud Account",
      type: "dynamic-select",
      required: true,
      description: accountDescription,
      dependsOn: "tenant_id",
      loadOptions: loadAccounts,
      searchable: true,
      excludeFromSubmit: true,
    },
  ];
}

// Shown in small text above a companion panel's result, so it's clear which
// account the keys/secret belong to.
const CLOUD_ACCOUNT_CONTEXT_FIELDS = [
  { field: "environment", label: "ENV" },
  { field: "master_account_id", label: "Master Account" },
  { field: "cloud_account_id", label: "Service Account" },
];

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString() : "—";
}

// Shows a raw Mongo value as text: lists comma-joined, booleans as Yes/No,
// nested objects as JSON, and anything missing as an empty "—".
function formatDbValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length > 0 ? value.map(formatDbValue).join(", ") : "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

// Shared "Generate Access & Secret Key" companion panel config (see
// CompanionPanel.jsx) — attached to any script whose page should offer it as
// a side panel rather than its own script card. Defined once since it's
// identical wherever it's used (same backend endpoint, same Mongo-backed
// dropdown chain), currently on every AWS script that takes access/secret keys.
const GENERATE_ACCESS_KEY_COMPANION_PANEL = {
  buttonLabel: "Generate Access & Secret Key",
  title: "Generate Access & Secret Key",
  scriptFile: "Generate_access_key_and_secret_key.py",
  endpoint: "/core/aws/generate-access-secret-key",
  submitLabel: "▶ Generate",
  runningLabel: "Generating...",
  againLabel: "Generate Again",
  // The IAM user credentials used server-side to call assume_role are
  // fixed (Backend/.env), not entered here — this just lets the panel
  // show what's configured, read-only, on demand.
  fixedCredentials: { endpoint: "/config/sts-credentials", label: "Show AWS Creds" },
  // Selecting a Cloud Account is what actually supplies role_arn/
  // external_id (from its `credentials`) — this names which input's
  // selected option carries them, rather than those being separate
  // visible/editable fields.
  sourceField: "cloud_account_id",
  sourceMissingMessage: "Could not find the selected cloud account's role details. Try reselecting it.",
  contextFields: CLOUD_ACCOUNT_CONTEXT_FIELDS,
  buildRequestBody: (selected) => ({
    role_arn: selected.assumeRoleArn,
    ...(selected.assumeRoleExternalId ? { external_id: selected.assumeRoleExternalId } : {}),
  }),
  // The selected account's own details from Mongo (native_details/
  // credentials) ride along with the result — not part of the API response,
  // but shown in the panel, and its region(s) let "Apply" also fill the main
  // form's Region field.
  enrichResult: (result, selected) => ({
    ...result,
    _accountRegions: selected.accountRegions || null,
    _bucketNameOrUri: selected.bucketNameOrUri,
    _accountType: selected.accountType,
    _assumeRoleArn: selected.assumeRoleArn,
    _assumeRoleExternalId: selected.assumeRoleExternalId,
    _assumeRoleMfaEnabled: selected.assumeRoleMfaEnabled,
  }),
  resultFields: [
    { key: "access_key", label: "Access Key", copy: true },
    { key: "secret_key", label: "Secret Key", copy: true },
    { key: "session_token", label: "Session Token", copy: true },
    { key: "_accountRegions", label: "Regions", format: formatDbValue },
    { key: "_bucketNameOrUri", label: "Bucket Name or URI", format: formatDbValue },
    { key: "_accountType", label: "Type", format: formatDbValue },
    { key: "_assumeRoleArn", label: "Assume Role ARN", format: formatDbValue },
    { key: "_assumeRoleExternalId", label: "Assume Role External ID", format: formatDbValue },
    { key: "_assumeRoleMfaEnabled", label: "Assume Role MFA Enabled", format: formatDbValue },
    { key: "expiration", label: "Expiration", format: formatDateTime },
    { key: "generated_at", label: "Generated At", format: formatDateTime },
  ],
  applyValues: (result) => ({
    access_key: result.access_key,
    secret_key: result.secret_key,
    session_token: result.session_token,
    region_names: result._accountRegions && result._accountRegions.length > 0 ? result._accountRegions : undefined,
  }),
  // No Role Session Name input — STS needs one, but the backend generates it
  // ("corestack-support-<timestamp>").
  inputs: cloudAccountPickerInputs({
    loadAccounts: loadCloudAccounts,
    accountDescription: "AWS cloud account whose assume-role ARN and external ID get used",
  }),
};

// Azure counterpart of GENERATE_ACCESS_KEY_COMPANION_PANEL: pick a CoreStack
// Azure cloud account, decrypt its stored credentials.application_secret
// server-side, and show it with the account's tenant/application/subscription
// details — "Apply" fills those into the script's own form. Attached to every
// Azure script that takes service-principal credentials.
const AZURE_DECRYPT_SECRET_COMPANION_PANEL = {
  buttonLabel: "Decrypt Secret Key",
  title: "Decrypt Secret Key",
  scriptFile: "Decrypt_azure_application_secret.py",
  endpoint: "/core/azure/decrypt-application-secret",
  submitLabel: "▶ Decrypt",
  runningLabel: "Decrypting...",
  againLabel: "Decrypt Another",
  sourceField: "cloud_account_id",
  sourceMissingMessage: "Could not find the selected cloud account's stored secret. Try reselecting it.",
  contextFields: CLOUD_ACCOUNT_CONTEXT_FIELDS,
  buildRequestBody: (selected) => ({
    application_secret: selected.encryptedSecret,
    cloud_account_name: selected.label,
    azure_tenant_id: selected.azureTenantId,
    application_id: selected.applicationId,
    subscription_id: selected.subscriptionId,
    subscription_name: selected.subscriptionName,
    account_type: selected.accountType,
  }),
  // Display-only native_details from Mongo, shown alongside the decrypted
  // result ("—" when the account doesn't have them).
  enrichResult: (result, selected) => ({
    ...result,
    _storageAccount: selected.storageAccount,
    _reportPath: selected.reportPath,
  }),
  resultFields: [
    { key: "tenant_id", label: "Tenant ID", copy: true },
    { key: "application_id", label: "Application (Client) ID", copy: true },
    { key: "application_secret", label: "Application Secret (decrypted)", copy: true },
    { key: "subscription_id", label: "Subscription ID", copy: true },
    { key: "subscription_name", label: "Subscription Name", format: formatDbValue },
    { key: "cloud_account_name", label: "Cloud Account", format: formatDbValue },
    { key: "type", label: "Type", format: formatDbValue },
    { key: "_storageAccount", label: "Storage Account", format: formatDbValue },
    { key: "_reportPath", label: "Report Path", format: formatDbValue },
    { key: "decrypted_at", label: "Decrypted At", format: formatDateTime },
  ],
  // Azure scripts name these fields differently (tenant_id/app_id/
  // client_secret vs application_id/application_secret, ...) — every common
  // alias is offered and the script page fills only the ones its form has.
  applyValues: (result) => ({
    tenant_id: result.tenant_id,
    azure_tenant_id: result.tenant_id,
    directory_id: result.tenant_id,
    application_id: result.application_id,
    app_id: result.application_id,
    client_id: result.application_id,
    application_secret: result.application_secret,
    client_secret: result.application_secret,
    app_secret: result.application_secret,
    subscription_id: result.subscription_id,
    azure_subscription_id: result.subscription_id,
  }),
  inputs: cloudAccountPickerInputs({
    loadAccounts: loadAzureCloudAccounts,
    accountDescription: "Azure cloud account whose stored application secret gets decrypted",
  }),
};

// AWS resource types this app's FinOps RI/Savings Plan scripts support —
// matches Backend/.../GetReservationSavingPlans.py's RI_RESOURCE_MAP/
// SP_RESOURCE_MAP keys exactly (any other value would be rejected server-side).
const RI_SP_RESOURCE_TYPE_OPTIONS = [
  { value: "EC2", label: "EC2" },
  { value: "RDS", label: "RDS" },
  { value: "ELASTICACHE", label: "ElastiCache" },
  { value: "REDSHIFT", label: "Redshift" },
  { value: "OPENSEARCH", label: "OpenSearch" },
];

// Which report sections to run — matches Backend/.../GetReservationSavingPlans.py's
// SERVICE_TYPES keys exactly. Selecting fewer means only those sections run
// (and only they appear in the output), not "run everything, show less".
const RI_SP_SERVICE_TYPE_OPTIONS = [
  { value: "ri_current_reservation", label: "RI Current Reservation" },
  { value: "ri_recommendations", label: "RI Recommendation" },
  { value: "ri_utilization", label: "RI Utilization" },
  { value: "savings_plans_current", label: "Current Savings Plans" },
  { value: "savings_plan_recommendations", label: "Recommendation Savings Plans" },
  { value: "savings_plan_utilization", label: "Savings Plan Utilization" },
  { value: "savings_plan_coverage", label: "Savings Coverage" },
];
const ALL_RI_SP_SERVICE_TYPES = RI_SP_SERVICE_TYPE_OPTIONS.map((opt) => opt.value);

// Standard AWS region codes — for the Reservation & Savings Plans Report's
// Region multi-select. RI current-reservation lookups are genuinely
// region-scoped by AWS, so picking several runs that section once per region
// and combines the results.
const AWS_REGION_OPTIONS = [
  { value: "us-east-1", label: "US East-1 (N. Virginia)" },
  { value: "us-east-2", label: "US East-2 (Ohio)" },
  { value: "us-west-1", label: "US West-1 (N. California)" },
  { value: "us-west-2", label: "US West-2 (Oregon)" },
  { value: "ca-central-1", label: "Canada Central-1 (Central)" },
  { value: "eu-west-1", label: "EU West-1 (Ireland)" },
  { value: "eu-west-2", label: "EU West-2 (London)" },
  { value: "eu-west-3", label: "EU West-3 (Paris)" },
  { value: "eu-central-1", label: "EU Central-1 (Frankfurt)" },
  { value: "eu-north-1", label: "EU North-1 (Stockholm)" },
  { value: "ap-south-1", label: "Asia South-1 (Mumbai)" },
  { value: "ap-southeast-1", label: "Asia Southeast-1 (Singapore)" },
  { value: "ap-southeast-2", label: "Asia Southeast-2 (Sydney)" },
  { value: "ap-northeast-1", label: "Asia Northeast-1 (Tokyo)" },
  { value: "ap-northeast-2", label: "Asia Northeast-2 (Seoul)" },
  { value: "ap-northeast-3", label: "Asia Northeast-3 (Osaka)" },
  { value: "sa-east-1", label: "South East-1 (São Paulo)" },
].map((opt) => ({ ...opt, label: `${opt.label} (${opt.value})` })); // e.g. "Asia Pacific (Mumbai) (ap-south-1)"

// Loads the per-region API base URLs configured in Backend/.env, once (they
// don't depend on anything else). `matchValue` is the region key, so the
// "API URL" field can auto-select the option matching whatever Environment
// is currently chosen.
async function loadRegionApiUrls() {
  const response = await fetch(`${API_BASE_URL}/config/region-api-urls`);
  if (!response.ok) {
    throw new Error(`Could not load API URLs (status ${response.status})`);
  }
  const data = await response.json(); // { us: "https://...", msprod: "https://...", ... }
  return Object.entries(data).map(([region, url]) => ({
    value: url,
    label: `${region.toUpperCase()} — ${url}`,
    matchValue: region,
  }));
}

// Bundles shown in the sidebar. Order here controls sidebar order.
export const MODULES = [
  { key: "core", label: "Core" },
  { key: "finops", label: "FinOps" },
  { key: "secops", label: "SecOps" },
  { key: "cloudops", label: "CloudOps" },
  { key: "reports", label: "Reports" },
  { key: "settings", label: "Settings" },
];

export const CLOUDS = ["aws", "azure", "gcp", "oci", "multicloud"];

// One entry per API endpoint. `inputs` drives the auto-generated run form.
// Field types: text | number | password | file | list (comma-separated -> array)
export const SCRIPTS = [
  {
    id: "core-aws-bulk-tenant-creation",
    module: "core",
    cloud: "aws",
    title: "Bulk Tenant Creation (Excel)",
    scriptFile: "Bulck_tenant_creations_using_excel.py",
    description:
      "Reads tenant names from an uploaded Excel file and creates a tenant for each row via the given API.",
    method: "POST",
    endpoint: "/core/aws/bulk-tenant-creation",
    requestType: "multipart/form-data",
    inputs: [
      {
        name: "environment",
        label: "Environment",
        type: "select",
        required: true,
        description: "CoreStack region — drives the Master Account list and auto-picks the API URL",
        options: ENVIRONMENTS,
        excludeFromSubmit: true,
      },
      {
        name: "api_url",
        label: "API URL",
        type: "async-select",
        required: true,
        description: "Tenant-creation API endpoint to call for each row — auto-selected from Environment, but can be overridden",
        loadOptions: loadRegionApiUrls,
        autoSelectFrom: "environment",
      },
      {
        name: "master_account_id",
        label: "Master Account",
        type: "dynamic-select",
        required: true,
        description: "Master account sent with each tenant payload (its id, not its name)",
        dependsOn: "environment",
        loadOptions: loadMasterAccountNames,
        searchable: true,
      },
      { name: "auth_token", label: "Auth Token", type: "password", required: true, description: "Sent as the X-Auth-Token header" },
      {
        name: "upload_mode",
        label: "Provide Tenant Names Via",
        type: "toggle",
        default: true,
        onLabel: "Upload File",
        offLabel: "Type Names",
        description: "On: upload an Excel file. Off: type tenant names directly, comma-separated.",
        excludeFromSubmit: true,
        groupWithNext: true,
      },
      {
        name: "excel_file",
        label: "Excel File",
        type: "file",
        required: (values) => values.upload_mode !== false,
        showWhen: (values) => values.upload_mode !== false,
        description: "Excel file containing the tenant names",
      },
      {
        name: "tenant_names",
        label: "Tenant Names",
        type: "list",
        required: (values) => values.upload_mode === false,
        showWhen: (values) => values.upload_mode === false,
        description: "Comma-separated tenant names to create directly, no file needed",
      },
      {
        name: "tenant_name_column",
        label: "Tenant Name Column",
        type: "text",
        required: (values) => values.upload_mode !== false,
        disabledWhen: (values) => values.upload_mode === false,
        description: "Exact column name in the Excel file that holds tenant names",
      },
      { name: "request_delay_seconds", label: "Request Delay (seconds)", type: "number", required: false, default: 0.5, description: "Delay between consecutive tenant-creation requests" },
    ],
    outputs: "results[]: { tenant_name, status: success|failed|error|skipped, status_code, response }",
  },
  {
    id: "core-aws-role-permissions",
    module: "core",
    cloud: "aws",
    title: "IAM Role Permissions",
    scriptFile: "Get_role_permission.py",
    description: "Lists the attached and inline IAM policies for a given role.",
    method: "POST",
    endpoint: "/core/aws/role-permissions",
    requestType: "application/json",
    inputs: [
      { name: "access_key", label: "Access Key", type: "password", required: true, description: "AWS access key ID" },
      { name: "secret_key", label: "Secret Key", type: "password", required: true, description: "AWS secret access key" },
      { name: "session_token", label: "Session Token", type: "password", required: true, description: "AWS session token" },
      { name: "role_name", label: "Role Name", type: "text", required: true, description: "IAM role name to inspect" },
    ],
    outputs: "{ attached_policies: [...], inline_policies: [...] }",
    // Not a script card of its own — a companion action opened as a side
    // panel from this script's page (button below Expand All/Collapse All),
    // since assuming the role to get temporary credentials is a natural
    // follow-on to inspecting its permissions.
    companionPanel: GENERATE_ACCESS_KEY_COMPANION_PANEL,
  },
  {
    id: "core-multicloud-bulk-sync-status",
    module: "core",
    cloud: "multicloud",
    title: "Bulk Sync Status Update",
    scriptFile: "BulkSyncStatus.py",
    description: "Posts a billing-sync status update for each service account ID.",
    method: "POST",
    endpoint: "/core/multicloud/bulk-sync-status",
    requestType: "application/json",
    inputs: [
      { name: "service_account_ids", label: "Service Account IDs", type: "list", required: true, description: "Comma-separated service account IDs to update" },
      { name: "base_url", label: "Base URL", type: "text", required: true, description: "URL template with a {} placeholder for the service account ID" },
      { name: "auth_token", label: "Auth Token", type: "password", required: true, description: "Sent as the X-Auth-Token header" },
      { name: "total_records_processed", label: "Total Records Processed", type: "number", required: false, default: 0, description: "Value sent in billing_info.total_records_processed" },
      { name: "request_delay_seconds", label: "Request Delay (seconds)", type: "number", required: false, default: 1, description: "Delay between consecutive requests" },
    ],
    outputs: "[{ service_account_id, status_code, response }]",
  },
  {
    id: "finops-aws-reservation-savings-plans-report",
    module: "finops",
    cloud: "aws",
    title: "Reservation & Savings Plans Report",
    scriptFile: "GetReservationSavingPlans.py",
    description:
      "Pulls current Reserved Instance and Savings Plan coverage, purchase recommendations, and utilization across EC2/RDS/ElastiCache/Redshift/OpenSearch, plus a diagnostic breakdown of any AWS calls that were denied.",
    method: "POST",
    endpoint: "/finops/aws/reservation-savings-plans-report",
    requestType: "application/json",
    inputs: [
      { name: "access_key", label: "Access Key", type: "password", required: true, description: "AWS access key ID" },
      { name: "secret_key", label: "Secret Key", type: "password", required: true, description: "AWS secret access key" },
      { name: "session_token", label: "Session Token", type: "password", required: true, description: "AWS session token" },
      {
        name: "region_names",
        label: "Region",
        type: "multi-select",
        required: true,
        default: ["us-east-1"],
        description: "AWS region(s) to query — RI current-reservation lookups run once per region selected here and combine",
        options: AWS_REGION_OPTIONS,
      },
      {
        name: "service_types",
        label: "Service Type",
        type: "multi-select",
        required: false,
        default: ALL_RI_SP_SERVICE_TYPES,
        description: "Which report sections to run — only the ones picked here are fetched and shown",
        options: RI_SP_SERVICE_TYPE_OPTIONS,
      },
      {
        name: "resource_types",
        label: "Resource Types",
        type: "multi-select",
        required: false,
        default: ["EC2", "RDS", "ELASTICACHE"],
        description: "AWS resource types to include in the report",
        options: RI_SP_RESOURCE_TYPE_OPTIONS,
      },
      {
        name: "term_in_years",
        label: "Term",
        type: "select",
        required: false,
        default: "ONE_YEAR",
        description: "Commitment term used for RI/Savings Plan purchase recommendations",
        options: [
          { value: "ONE_YEAR", label: "1 Year" },
          { value: "THREE_YEARS", label: "3 Years" },
        ],
      },
      {
        name: "payment_options",
        label: "Payment Option",
        type: "multi-select",
        required: false,
        default: ["NO_UPFRONT"],
        description: "Upfront payment option(s) used for RI/Savings Plan purchase recommendations — recommendations are fetched once per option selected here",
        options: [
          { value: "NO_UPFRONT", label: "No Upfront" },
          { value: "PARTIAL_UPFRONT", label: "Partial Upfront" },
          { value: "ALL_UPFRONT", label: "All Upfront" },
        ],
      },
      {
        name: "granularity",
        label: "RI Utilization Granularity",
        type: "select",
        required: false,
        default: "MONTHLY",
        description: "Granularity of the RI utilization breakdown",
        options: [
          { value: "MONTHLY", label: "Monthly" },
          { value: "DAILY", label: "Daily" },
        ],
      },
      {
        name: "start_date",
        label: "Start Date",
        type: "date",
        required: false,
        description: "Start of the date range for utilization/coverage data. Leave both dates blank to default to month-to-date.",
      },
      {
        name: "end_date",
        label: "End Date",
        type: "date",
        required: false,
        maxToday: true,
        description: "End of the date range for utilization/coverage data — can't be in the future. Leave both dates blank to default to month-to-date.",
      },
    ],
    outputs: "One table per selected Service Type, in that order (skips whichever weren't selected): ri_current_reservation[] (enriched with each reservation's own utilization — Reservation Hours Used/Unused, Utilization %, Net Savings, Purchased Hours), ri_recommendations[], ri_utilization[] (one row per individual reservation, not aggregated), savings_plans_current[] (enriched with each plan's own utilization %), savings_plan_recommendations[], savings_plan_utilization[] (one row per individual Savings Plan), savings_plan_coverage[]. Every row uses plain-English column headers (no raw AWS field names), plus diagnostics[] (any AWS calls that were denied or failed, with a deny_type explained in legend) and legend.",
    // Same companion action as "IAM Role Permissions" — generating temporary
    // credentials for a role is a natural follow-on here too, since this
    // report itself needs AWS access/secret keys to run.
    companionPanel: GENERATE_ACCESS_KEY_COMPANION_PANEL,
  },
  {
    id: "finops-azure-download-cost-details-ea-account",
    module: "finops",
    cloud: "azure",
    title: "Download EA Cost Details",
    scriptFile: "Dwonload_cost_details_EA_account.py",
    description:
      "Finds the storage account's resource group, fetches its key, lists every blob in the given container/directory, and reads the most recent one matching the days_ago threshold. Everything fetched is returned directly — nothing is saved to disk, and no CSV file is created anywhere.",
    method: "POST",
    endpoint: "/finops/azure/download-cost-details-ea-account",
    requestType: "application/json",
    // Runs as a resumable background job instead of a single streamed request:
    // the fetch can be large and slow enough that surviving a page refresh
    // matters, and the full result is served as a real file download rather
    // than held in page memory.
    resultMode: "job",
    inputs: [
      { name: "tenant_id", label: "Tenant ID", type: "text", required: true, description: "Azure AD tenant ID" },
      { name: "app_id", label: "App ID", type: "text", required: true, description: "Service principal (app) ID" },
      { name: "client_secret", label: "Client Secret", type: "password", required: true, description: "Service principal client secret" },
      { name: "subscription_id", label: "Subscription ID", type: "text", required: true, description: "Azure subscription ID containing the storage account" },
      { name: "storage_account_name", label: "Storage Account Name", type: "text", required: true, description: "Storage account to search" },
      { name: "container_name", label: "Container Name", type: "text", required: true, description: "Blob container name" },
      { name: "directory_path", label: "Directory Path", type: "text", required: true, description: "Directory/prefix inside the container to search" },
      { name: "days_ago", label: "Days Ago", type: "number", required: false, default: 0, description: "Selects the blob dated this many days before the most recent blob" },
    ],
    outputs: "{ available_blobs, matched_blob, resource_group, filename, columns, rows, row_count }. Each entry in rows is a plain array of values in columns order (not one object per row) to keep large exports compact — the UI reconstructs the table from columns + rows. Empty if no blob matched the threshold.",
    companionPanel: AZURE_DECRYPT_SECRET_COMPANION_PANEL,
  },
  {
    id: "secops-multicloud-bulk-compliance-standards-execution",
    module: "secops",
    cloud: "multicloud",
    title: "Bulk Compliance Standards Execution",
    scriptFile: "BulkComplianceStandardsExecution.py",
    description: "For every tenant, executes the matching compliance standards against every active cloud account.",
    method: "POST",
    endpoint: "/secops/multicloud/bulk-compliance-standards-execution",
    requestType: "application/json",
    inputs: [
      { name: "base_url", label: "Base URL", type: "text", required: true, description: "Base URL of the CoreStack API" },
      { name: "auth_token", label: "Auth Token", type: "password", required: true, description: "Sent as the X-Auth-Token header" },
      { name: "target_compliances", label: "Target Compliances", type: "list", required: true, description: "Comma-separated compliance standard names to execute" },
    ],
    outputs: "[{ tenant_id, executions: [{ cloud_account_id, compliance_uri, status, response|error }] }]",
  },
  {
    id: "settings-create-user-group",
    module: "settings",
    cloud: null,
    title: "Create User Group",
    scriptFile: "Create_user_groups.py",
    description:
      "Fetches all tenants under the master account, matches roles by name across those tenants, and creates a user group with the matched roles and given users.",
    method: "POST",
    endpoint: "/settings/create-user-group",
    requestType: "application/json",
    inputs: [
      { name: "base_url", label: "Base URL", type: "text", required: true, description: "Base URL of the CoreStack API" },
      { name: "master_account_id", label: "Master Account ID", type: "text", required: true, description: "Master account ID to fetch tenants from" },
      { name: "auth_token", label: "Auth Token", type: "password", required: true, description: "Sent as the X-Auth-Token header" },
      { name: "user_ids", label: "User IDs", type: "list", required: true, description: "Comma-separated user IDs to add to the group" },
      { name: "group_name", label: "Group Name", type: "text", required: true, description: "Name of the user group to create" },
      { name: "required_role_ids", label: "Required Role Names", type: "list", required: true, description: "Comma-separated role names to match and attach to the group" },
    ],
    outputs: "{ payload, response, tenant_roles } on success, { error, tenant_roles } if no roles matched, or { payload, error, tenant_roles } if group creation failed. Nothing is written to disk — tenant_roles carries the full per-tenant role listing that used to go to debug_all_roles.json.",
  },
  {
    id: "finops-aws-s3-buket-details",
    module: "finops",
    cloud: "aws",
    title: "S3_buket_details",
    scriptFile: "S3_Buket_Details.py",
    description: "Lists all S3 objects (files/folders) in a specified bucket that were last modified within a given date range, returning their keys and last-modified timestamps.",
    method: "POST",
    endpoint: "/finops/aws/s3-buket-details",
    requestType: "application/json",
    inputs: [
      {
        name: "access_key",
        label: "Access Key",
        type: "password",
        required: true,
        description: "AWS access key id",
      },
      {
        name: "secret_key",
        label: "Secret Key",
        type: "password",
        required: true,
        description: "AWS secret access key",
      },
      {
        name: "session_token",
        label: "Session Token",
        type: "password",
        required: true,
        description: "AWS session token",
      },
      {
        name: "bucket_name",
        label: "Bucket Name",
        type: "text",
        required: true,
        description: "Name of the S3 bucket to inspect",
      },
      {
        name: "start_date",
        label: "Start Date",
        type: "date",
        required: true,
        description: "Start of the date range to filter objects by last modified date, format YYYY-MM-DD",
      },
      {
        name: "end_date",
        label: "End Date",
        type: "date",
        required: true,
        maxToday: true,
        description: "End of the date range to filter objects by last modified date, format YYYY-MM-DD",
      },
    ],
    outputs: "A dict with bucket_name, start_date, end_date, file_count, and a files list of objects each containing file_name and last_modified.",
    companionPanel: GENERATE_ACCESS_KEY_COMPANION_PANEL,
  },
  {
    id: "core-aws-aws-config-rules-inventory-across-all-regions",
    module: "core",
    cloud: "aws",
    title: "AWS Config Rules Inventory Across All Regions",
    scriptFile: "Aws_Config_Rules_Inventory_Across_All_Regions.py",
    description: "Connects to AWS with the given credentials, scans every AWS region where AWS Config is available, and collects details about each AWS Config rule found (region, rule name, description, source identifier, input parameters, and resource scope).",
    method: "POST",
    endpoint: "/core/aws/aws-config-rules-inventory-across-all-regions",
    requestType: "application/json",
    inputs: [
      {
        name: "access_key",
        label: "Access Key",
        type: "password",
        required: true,
        description: "AWS access key id used to authenticate",
      },
      {
        name: "secret_key",
        label: "Secret Key",
        type: "password",
        required: true,
        description: "AWS secret access key used to authenticate",
      },
      {
        name: "session_token",
        label: "Session Token",
        type: "password",
        required: true,
        description: "AWS session token used to authenticate",
      },
    ],
    outputs: "Returns a dict with 'config_rules' (a flat list of row objects, each containing region, config_rule_name, description, source, input_parameters, and scope) and a 'total_count' of rules found across all regions.",
    companionPanel: GENERATE_ACCESS_KEY_COMPANION_PANEL,
  },
  {
    id: "finops-azure-azure-ea-account-billing-periods-details",
    module: "finops",
    cloud: "azure",
    title: "Azure EA account Billing Periods Details",
    scriptFile: "Azure_Ea_Account_Billing_Periods_Details.py",
    description: "Authenticates to Azure AD via a service principal, discovers (or uses a supplied list of) subscriptions, and retrieves each subscription's EA Billing Periods for the last 12 months, returning a consolidated list of billing period rows, any per-subscription errors, and summary statistics.",
    method: "POST",
    endpoint: "/finops/azure/azure-ea-account-billing-periods-details",
    requestType: "application/json",
    inputs: [
      {
        name: "tenant_id",
        label: "Tenant ID",
        type: "password",
        required: true,
        description: "Azure AD tenant ID for the service principal used to authenticate",
      },
      {
        name: "application_id",
        label: "Application (Client) ID",
        type: "password",
        required: true,
        description: "Azure AD app registration (service principal) client ID",
      },
      {
        name: "application_secret",
        label: "Application Secret",
        type: "password",
        required: true,
        description: "Client secret for the Azure AD app registration",
      },
      {
        name: "azure_subscription_ids",
        label: "Subscription IDs",
        type: "list",
        required: false,
        description: "Comma-separated list of Azure subscription IDs to check. Leave empty to auto-discover every subscription the service principal can see.",
      },
    ],
    outputs: "Returns a dict with 'billing_periods' (a flat list of per-subscription billing period rows), 'errors' (a list of subscriptions that failed with their error message), 'summary' (a list of label/value stats about coverage and date ranges), and counts total_subscriptions, total_rows, and total_errors.",
    companionPanel: AZURE_DECRYPT_SECRET_COMPANION_PANEL,
  },
];
