"""
Azure EA - Billing Periods Export
---------------------------------
Authenticates with an Azure AD app registration (client credentials),
calls the Billing Periods API for each subscription:

  GET https://management.azure.com/subscriptions/{SubscriptionID}/providers/
      Microsoft.Billing/billingPeriods?api-version=2018-03-01-preview

and returns the consolidated results.
"""

import os
import time
from datetime import datetime, timezone

import requests

ARM_BASE = "https://management.azure.com"
BILLING_API_VERSION = "2018-03-01-preview"
SUBSCRIPTIONS_API_VERSION = "2020-01-01"
MAX_RETRIES = 5

# Report window: last N months including the current month.
# NOTE: the Billing Periods API itself only exposes a limited history (~8 months);
# it does not support $filter/$top for older periods, and older periods return 404.
LOOKBACK_MONTHS = int(os.getenv("LOOKBACK_MONTHS", "12"))


def window_start(months: int) -> str:
    """First day of the month (months-1) months before the current month, 'YYYY-MM-DD'."""
    now = datetime.now(timezone.utc)
    total = now.year * 12 + (now.month - 1) - (months - 1)
    return f"{total // 12:04d}-{total % 12 + 1:02d}-01"


WINDOW_START = window_start(LOOKBACK_MONTHS)


# ---------------------------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------------------------
def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get an ARM bearer token using the client-credentials flow."""
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://management.azure.com/.default",
    }
    resp = requests.post(url, data=data, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Token request failed ({resp.status_code}): {resp.text}")
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# HTTP helper with retry (handles 429 throttling and transient 5xx)
# ---------------------------------------------------------------------------
def arm_get(url: str, token: str, params: dict = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = None
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = int(resp.headers.get("Retry-After", 2 ** attempt))
            time.sleep(wait)
            continue
        return resp
    return resp


def get_all_pages(url: str, token: str, params: dict = None) -> list:
    """Follow nextLink pagination and return all 'value' items."""
    items = []
    while url:
        resp = arm_get(url, token, params)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        body = resp.json()
        items.extend(body.get("value", []))
        url = body.get("nextLink")
        params = None  # nextLink already contains the query string
    return items


# ---------------------------------------------------------------------------
# DATA COLLECTION
# ---------------------------------------------------------------------------
def list_subscriptions(token: str) -> list:
    url = f"{ARM_BASE}/subscriptions"
    subs = get_all_pages(url, token, {"api-version": SUBSCRIPTIONS_API_VERSION})
    return [{"id": s["subscriptionId"], "name": s.get("displayName", "")} for s in subs]


def get_billing_periods(subscription_id: str, token: str) -> list:
    """Billing periods ending within the last LOOKBACK_MONTHS months."""
    url = f"{ARM_BASE}/subscriptions/{subscription_id}/providers/Microsoft.Billing/billingPeriods"
    periods = get_all_pages(url, token, {"api-version": BILLING_API_VERSION})
    return [
        p for p in periods
        if ((p.get("properties") or {}).get("billingPeriodEndDate") or "")[:10] >= WINDOW_START
    ]


def flatten_period(sub_id: str, sub_name: str, period: dict) -> dict:
    props = period.get("properties", {}) or {}
    invoice_ids = props.get("invoiceIds") or []
    return {
        "Subscription ID": sub_id,
        "Subscription Name": sub_name,
        "Status": "Has Billing Periods",
        "Billing Period Name": period.get("name", ""),
        "Billing Period Start Date": props.get("billingPeriodStartDate", ""),
        "Billing Period End Date": props.get("billingPeriodEndDate", ""),
        "Invoice IDs": ", ".join(i.split("/")[-1] for i in invoice_ids),
        "Type": period.get("type", ""),
        "Resource ID": period.get("id", ""),
    }


def to_month(date_str: str) -> str:
    """'2024-03-01' / '2024-03-01T00:00:00Z' -> 'Mar 2024'."""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").strftime("%b %Y")
    except (TypeError, ValueError):
        return date_str or ""


def build_summary(sub_stats: list) -> list:
    """Summary lines describing the overall billing period coverage."""
    with_bp = [s for s in sub_stats if s["status"] == "Has Billing Periods"]
    without_bp = [s for s in sub_stats if s["status"] == "No Billing Periods"]
    errored = [s for s in sub_stats if s["status"] == "Error"]

    starts = [s["start"] for s in with_bp if s["start"]]
    ends = [s["end"] for s in with_bp if s["end"]]
    overall = f"{to_month(min(starts))} to {to_month(max(ends))}" if starts and ends else "N/A"

    now_month = datetime.now(timezone.utc).strftime("%b %Y")
    months_found = len({s for st in with_bp for s in st["months"]})
    lines = [
        (f"Requested window (last {LOOKBACK_MONTHS} months)", f"{to_month(WINDOW_START)} to {now_month}"),
        ("Months available from Azure in this window", f"{months_found} of {LOOKBACK_MONTHS}"),
        ("Total number of accounts", len(sub_stats)),
        (f"Accounts having billing periods ({overall})", len(with_bp)),
        ("Accounts NOT having any billing periods", len(without_bp)),
    ]
    if errored:
        lines.append(("Accounts failed with error", len(errored)))

    ranges = {}
    for s in with_bp:
        key = f"{to_month(s['start'])} to {to_month(s['end'])}"
        ranges[key] = ranges.get(key, 0) + 1
    if ranges:
        lines.append(("Billing period range", "No. of accounts"))
        lines.extend(sorted(ranges.items()))
    return lines


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def get_azure_billing_periods(tenant_id, application_id, application_secret, azure_subscription_ids=None, progress_callback=None):
    try:
        token = get_access_token(tenant_id, application_id, application_secret)

        subscription_ids = [s.strip() for s in (azure_subscription_ids or "").split(",") if s.strip()]
        if subscription_ids:
            subscriptions = [{"id": s, "name": ""} for s in subscription_ids]
        else:
            subscriptions = list_subscriptions(token)

        rows, errors, sub_stats = [], [], []
        total = len(subscriptions)
        for i, sub in enumerate(subscriptions, start=1):
            base = {"Subscription ID": sub["id"], "Subscription Name": sub["name"]}
            try:
                periods = get_billing_periods(sub["id"], token)
                if periods:
                    flat = [flatten_period(sub["id"], sub["name"], p) for p in periods]
                    rows.extend(flat)
                    starts = [r["Billing Period Start Date"] for r in flat if r["Billing Period Start Date"]]
                    ends = [r["Billing Period End Date"] for r in flat if r["Billing Period End Date"]]
                    sub_stats.append({
                        "status": "Has Billing Periods",
                        "start": min(starts) if starts else "",
                        "end": max(ends) if ends else "",
                        "months": {r["Billing Period Name"] for r in flat},
                    })
                else:
                    rows.append({**base, "Status": "No Billing Periods"})
                    sub_stats.append({"status": "No Billing Periods", "start": "", "end": "", "months": set()})
            except Exception as exc:
                errors.append({**base, "Error": str(exc)})
                rows.append({**base, "Status": "Error"})
                sub_stats.append({"status": "Error", "start": "", "end": "", "months": set()})

            if progress_callback:
                progress_callback(i, total)

        summary = build_summary(sub_stats)
        summary_list = [{"label": label, "value": value} for label, value in summary]

        return {
            "billing_periods": rows,
            "errors": errors,
            "summary": summary_list,
            "total_subscriptions": total,
            "total_rows": len(rows),
            "total_errors": len(errors),
        }
    except Exception as e:
        return {"error": str(e)}
