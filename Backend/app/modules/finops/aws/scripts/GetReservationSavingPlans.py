from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

# ============================================================
# RESOURCE MAPS
# ============================================================
RI_RESOURCE_MAP = {
    "EC2": {"display": "EC2", "ce_service": "Amazon Elastic Compute Cloud - Compute", "kind": "ec2"},
    "RDS": {"display": "RDS", "ce_service": "Amazon Relational Database Service", "kind": "rds"},
    "ELASTICACHE": {"display": "ElastiCache", "ce_service": "Amazon ElastiCache", "kind": "elasticache"},
    "REDSHIFT": {"display": "Redshift", "ce_service": "Amazon Redshift", "kind": "redshift"},
    "OPENSEARCH": {"display": "OpenSearch", "ce_service": "Amazon OpenSearch Service", "kind": "opensearch"},
}

SP_RESOURCE_MAP = {
    "EC2": {"display": "EC2", "ce_service": "Amazon Elastic Compute Cloud - Compute"},
    "RDS": {"display": "RDS", "ce_service": "Amazon Relational Database Service"},
    "ELASTICACHE": {"display": "ElastiCache", "ce_service": "Amazon ElastiCache"},
    "REDSHIFT": {"display": "Redshift", "ce_service": "Amazon Redshift"},
    "OPENSEARCH": {"display": "OpenSearch", "ce_service": "Amazon OpenSearch Service"},
}

# Which Savings Plans "type" to request recommendations for, per resource —
# "Database Savings Plans" (DATABASE_SP) is what actually covers RDS/
# ElastiCache/Redshift/OpenSearch; only EC2 uses the general-purpose compute
# type. Requesting COMPUTE_SP for all of them (as this script used to)
# always came back empty for the non-EC2 ones since that type simply doesn't
# apply to them.
SP_TYPE_BY_RESOURCE = {
    "EC2": "COMPUTE_SP",
    "RDS": "DATABASE_SP",
    "ELASTICACHE": "DATABASE_SP",
    "REDSHIFT": "DATABASE_SP",
    "OPENSEARCH": "DATABASE_SP",
}

# Cost Explorer's RI/Savings Plan purchase-recommendation lookback window is
# an enum (SEVEN_DAYS | THIRTY_DAYS | SIXTY_DAYS), not an arbitrary number of
# hours/days — THIRTY_DAYS is the widest commonly useful option.
LOOKBACK_PERIOD_DAYS = "THIRTY_DAYS"

# Every state a Savings Plan can be in — passed explicitly to
# DescribeSavingsPlans so its (undocumented either way) default can't ever
# silently exclude some of them.
ALL_SAVINGS_PLAN_STATES = [
    "payment-pending", "payment-failed", "active", "retired",
    "queued", "queued-deleted", "pending-return", "returned",
]

LEGEND = {
    "IMPLICIT_DENY": "Permission is simply MISSING. Fix: add the action to the IAM policy.",
    "EXPLICIT_DENY": (
        "A Deny is overriding an Allow. Fix: check role policy, permissions boundary, "
        "AND Organizations SCPs (SCPs won't show in iam:GetRolePolicy)."
    ),
}

# One report section per selectable "Service Type" in the UI — the key here
# is also the key it's returned under, and the order here is the order
# sections run in and are returned in (skipping whichever aren't selected).
SERVICE_TYPES = [
    "ri_current_reservation",
    "ri_recommendations",
    "ri_utilization",
    "savings_plans_current",
    "savings_plan_recommendations",
    "savings_plan_utilization",
    "savings_plan_coverage",
]


# ============================================================
# HELPERS
# ============================================================
def normalize_resource_types(resource_types=None, resource_map=None):
    if resource_map is None:
        resource_map = RI_RESOURCE_MAP

    if resource_types is None:
        resource_types = list(resource_map.keys())
    elif isinstance(resource_types, str):
        resource_types = [resource_types]

    normalized = []
    for item in resource_types:
        value = str(item).strip().upper()
        if value in resource_map:
            normalized.append(value)
        else:
            alias = value.replace(" ", "_")
            match = next((key for key in resource_map if key.replace(" ", "_") == alias), None)
            if match:
                normalized.append(match)
            else:
                raise ValueError(f"Unsupported resource type: {item}")

    unique = []
    for item in normalized:
        if item not in unique:
            unique.append(item)
    return unique


def normalize_service_types(service_types=None):
    """Which report sections to run — defaults to all of them (the original,
    full-report behavior) when not specified. Unrecognized values are
    dropped rather than rejected, since the UI only ever offers the known
    ones anyway."""
    if service_types is None:
        return list(SERVICE_TYPES)
    selected = [s for s in service_types if s in SERVICE_TYPES]
    return selected or list(SERVICE_TYPES)


def get_current_month_window():
    today = datetime.utcnow()
    start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = today
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def classify_access_denied(error_message):
    if not error_message:
        return "UNKNOWN"

    msg = error_message.lower()
    if "with an explicit deny" in msg:
        return "EXPLICIT_DENY"
    if "because no identity-based policy allows" in msg:
        return "IMPLICIT_DENY"
    return "UNKNOWN"


def record_api_error(diagnostics, title, error, action_name=None):
    if isinstance(error, ClientError):
        aws_code = error.response["Error"].get("Code")
        aws_message = error.response["Error"].get("Message")
        deny_type = classify_access_denied(aws_message) if aws_code == "AccessDeniedException" else "N/A"
        diagnostics.append({
            "action": action_name or title,
            "status": aws_code,
            "deny_type": deny_type,
            "detail": aws_message,
        })
    else:
        diagnostics.append({
            "action": action_name or title,
            "status": "OTHER_ERROR",
            "deny_type": "N/A",
            "detail": str(error),
        })


def is_data_unavailable(error):
    return isinstance(error, ClientError) and error.response["Error"].get("Code") == "DataUnavailableException"


def error_row(label, error):
    return {"Resource Type": label, "Error": str(error)}


def note_row(label, note):
    return {"Resource Type": label, "Note": note}


# Human-readable labels for the enums this script sends/receives — shown in
# the output instead of the raw AWS constant, since this report is meant to
# be readable without AWS background.
_LOOKBACK_LABELS = {"SEVEN_DAYS": "7 Days", "THIRTY_DAYS": "30 Days", "SIXTY_DAYS": "60 Days"}
_TERM_LABELS = {"ONE_YEAR": "1 Year", "THREE_YEARS": "3 Years"}
_PAYMENT_OPTION_LABELS = {
    "NO_UPFRONT": "No Upfront",
    "PARTIAL_UPFRONT": "Partial Upfront",
    "ALL_UPFRONT": "All Upfront",
    "LIGHT_UTILIZATION": "Light Utilization",
    "MEDIUM_UTILIZATION": "Medium Utilization",
    "HEAVY_UTILIZATION": "Heavy Utilization",
}


def format_lookback_period(value):
    return _LOOKBACK_LABELS.get(value, value)


def format_term(value):
    return _TERM_LABELS.get(value, value)


def format_payment_option(value):
    return _PAYMENT_OPTION_LABELS.get(value, value)


def term_label_from_seconds(seconds):
    if seconds is None:
        return None
    try:
        years = round(int(seconds) / 31536000)
    except (TypeError, ValueError):
        return None
    return f"{years} Year" + ("" if years == 1 else "s")


def account_id_from_arn(arn):
    # arn:partition:service:region:account-id:resource — account ID is
    # always the 5th colon-separated segment.
    if not arn:
        return None
    parts = arn.split(":")
    return parts[4] if len(parts) > 4 else None


def savings_plan_id_from_arn(arn):
    # .../savingsplan/<id> — the ID is whatever follows the last "/".
    if not arn:
        return None
    return arn.rsplit("/", 1)[-1]


# InstanceDetails (RI recommendations) wraps exactly one key depending on the
# resource type — e.g. {"EC2InstanceDetails": {...}}, {"RDSInstanceDetails":
# {...}} — this pulls whichever one is present and renames its fields to
# plain-English columns instead of leaving the whole thing as one nested cell.
def flatten_instance_details(instance_details):
    details = next(iter((instance_details or {}).values()), {}) or {}
    return {
        "Instance Family": details.get("Family"),
        "Reservation SKU": details.get("InstanceType") or details.get("NodeType") or details.get("InstanceClass"),
        "Region": details.get("Region"),
        "Availability Zone": details.get("AvailabilityZone"),
        "Platform": details.get("Platform"),
        "Database Engine": details.get("DatabaseEngine"),
        "Current Generation": details.get("CurrentGeneration"),
    }


# SavingsPlansDetails (Savings Plan recommendations) is a flat dict already,
# just renamed here for consistency with the rest of this table.
def flatten_savings_plan_details(savings_plans_details):
    details = savings_plans_details or {}
    return {
        "Instance Family": details.get("InstanceFamily"),
        "Region": details.get("Region"),
    }


# ============================================================
# RI CURRENT RESERVATION + PER-RESERVATION UTILIZATION
# ============================================================
def get_ri_utilization_by_reservation(clients, diagnostics, resource_types=None, start_date=None, end_date=None, region_names=None):
    """Per-individual-reservation utilization (GroupBy SUBSCRIPTION_ID —
    the only dimension GetReservationUtilization can group by), rather than
    one row aggregated across every reservation of a resource type. Used
    both as the standalone "RI Utilization" table and to enrich "RI Current
    Reservation" with usage figures for each specific reservation. Returns
    (rows, records) — records maps every known identifier of a reservation
    (lease ID and subscription ID) to {"utilization", "attributes", "label"}.
    GroupBy can't be combined with Granularity, so this doesn't take one."""
    resource_types = normalize_resource_types(resource_types, RI_RESOURCE_MAP)
    if start_date is None or end_date is None:
        start_date, end_date = get_current_month_window()

    rows = []
    records = {}

    for resource in resource_types:
        config = RI_RESOURCE_MAP[resource]
        label = config["display"]

        service_filter = {"Dimensions": {"Key": "SERVICE", "Values": [config["ce_service"]]}}
        if region_names:
            # Cost Explorer is account/org-wide — restrict it to the regions
            # selected in the UI so this table matches RI Current Reservation.
            ce_filter = {"And": [service_filter, {"Dimensions": {"Key": "REGION", "Values": list(region_names)}}]}
        else:
            ce_filter = service_filter

        try:
            groups_seen = False
            next_token = None
            while True:
                request = {
                    "TimePeriod": {"Start": start_date, "End": end_date},
                    "Filter": ce_filter,
                    "GroupBy": [{"Type": "DIMENSION", "Key": "SUBSCRIPTION_ID"}],
                }
                if next_token:
                    request["NextPageToken"] = next_token
                response = clients["ce"].get_reservation_utilization(**request)

                for entry in response.get("UtilizationsByTime", []):
                    time_period = entry.get("TimePeriod", {})
                    for group in entry.get("Groups", []):
                        groups_seen = True
                        # Each group is {"Key": "SubscriptionId", "Value": "<id>",
                        # "Attributes": {...}} — "Key" is just the dimension
                        # name, so it must never be used as the ID itself. The
                        # reservation ID users recognise (and that the
                        # describe-reserved-* APIs return) is the "leaseId"
                        # attribute; the subscription ID is CE's own billing ID.
                        attributes = group.get("Attributes") or {}
                        subscription_id = attributes.get("subscriptionId") or group.get("Value")
                        reservation_id = attributes.get("leaseId") or subscription_id
                        utilization = group.get("Utilization", {})
                        rows.append({
                            "Resource Type": label,
                            "Reservation ID": reservation_id,
                            "Subscription ID": subscription_id,
                            "Account ID": attributes.get("accountId"),
                            "Region": attributes.get("region"),
                            "Instance Type": attributes.get("instanceType"),
                            "Number of Instances": attributes.get("numberOfInstances"),
                            "Status": attributes.get("status"),
                            "Period Start": time_period.get("Start"),
                            "Period End": time_period.get("End"),
                            "Utilization (%)": utilization.get("UtilizationPercentage"),
                            "Purchased Hours": utilization.get("PurchasedHours"),
                            "Reservation Hours Used": utilization.get("TotalActualHours"),
                            "Reservation Hours Unused": utilization.get("UnusedHours"),
                            "Net Savings": utilization.get("NetRISavings"),
                            "Realized Savings": utilization.get("RealizedSavings"),
                            "Unrealized Savings": utilization.get("UnrealizedSavings"),
                        })
                        record = {"utilization": utilization, "attributes": attributes, "label": label}
                        for key in {reservation_id, subscription_id}:
                            if key:
                                records[key] = record

                next_token = response.get("NextPageToken")
                if not next_token:
                    break

            if not groups_seen:
                rows.append(note_row(label, "No utilization data for this resource type in the selected date range / regions"))
        except Exception as e:
            record_api_error(diagnostics, f"{label} RI UTILIZATION ERROR", e, action_name=f"ce:GetReservationUtilization:{label}")
            rows.append(error_row(label, e))

    return rows, records


def get_ri_current_reservations(clients, diagnostics, resource_types=None, region_name=None, utilization_records=None, matched_ids=None):
    """matched_ids (a set, optional) collects every Cost Explorer record key
    that was matched to a reservation found here, so the caller can tell
    which reservations CE knows about but these describe APIs didn't return."""
    resource_types = normalize_resource_types(resource_types, RI_RESOURCE_MAP)
    utilization_records = utilization_records or {}
    if matched_ids is None:
        matched_ids = set()
    rows = []

    for resource in resource_types:
        config = RI_RESOURCE_MAP[resource]
        label = config["display"]

        try:
            if resource == "EC2":
                response = clients["ec2"].describe_reserved_instances(Filters=[{"Name": "state", "Values": ["active"]}])
                reservations = response.get("ReservedInstances", [])
            elif resource == "RDS":
                reservations = []
                marker = None
                while True:
                    request = {"MaxRecords": 100}
                    if marker:
                        request["Marker"] = marker
                    response = clients["rds"].describe_reserved_db_instances(**request)
                    reservations.extend(response.get("ReservedDBInstances", []))
                    marker = response.get("Marker")
                    if not marker:
                        break
            elif resource == "ELASTICACHE":
                reservations = []
                marker = None
                while True:
                    request = {"MaxRecords": 100}
                    if marker:
                        request["Marker"] = marker
                    response = clients["elasticache"].describe_reserved_cache_nodes(**request)
                    reservations.extend(response.get("ReservedCacheNodes", []))
                    marker = response.get("Marker")
                    if not marker:
                        break
            elif resource == "REDSHIFT":
                reservations = []
                marker = None
                while True:
                    request = {"MaxRecords": 100}
                    if marker:
                        request["Marker"] = marker
                    response = clients["redshift"].describe_reserved_nodes(**request)
                    reservations.extend(response.get("ReservedNodes", []))
                    marker = response.get("Marker")
                    if not marker:
                        break
            elif resource == "OPENSEARCH":
                reservations = []
                next_token = None
                while True:
                    request = {"MaxResults": 100}
                    if next_token:
                        request["NextToken"] = next_token
                    response = clients["opensearch"].describe_reserved_instances(**request)
                    reservations.extend(response.get("ReservedInstances", []))
                    next_token = response.get("NextToken")
                    if not next_token:
                        break
            else:
                reservations = []

            if not reservations:
                # Nothing to show for this resource type — skip it entirely
                # rather than adding a placeholder row. (Reservations are
                # region-specific, unlike everything else in this report — if
                # this is unexpectedly empty, double check the region above
                # matches where they were actually purchased.)
                continue

            for item in reservations:
                reservation_id = (
                    item.get("ReservedInstancesId")  # EC2 (plural "Instances")
                    or item.get("ReservedDBInstanceId")  # RDS
                    or item.get("ReservedCacheNodeId")  # ElastiCache
                    or item.get("ReservedNodeId")  # Redshift
                    or item.get("ReservedInstanceId")  # OpenSearch (singular "Instance")
                )
                start = item.get("Start") or item.get("StartTime")
                end = item.get("End")
                if end is None and start is not None and item.get("Duration") is not None:
                    try:
                        end = start + timedelta(seconds=int(item["Duration"]))
                    except (TypeError, ValueError):
                        end = None

                # Cost Explorer keys reservations by "leaseId" — the same as
                # the reservation ID for EC2/Redshift/OpenSearch, but for RDS
                # ReservedDBInstanceId is a user-chosen name and the matching
                # value is its separate "LeaseId" field.
                record = None
                for candidate in (item.get("LeaseId"), reservation_id):
                    if candidate and candidate in utilization_records:
                        record = utilization_records[candidate]
                        break
                if record:
                    matched_ids.update(
                        key for key, value in utilization_records.items() if value is record
                    )
                utilization = (record or {}).get("utilization", {})

                rows.append({
                    "Resource Type": label,
                    "Reservation SKU": (
                        item.get("InstanceType") or item.get("DBInstanceClass")
                        or item.get("CacheNodeType") or item.get("NodeType")
                    ),
                    "Region": region_name,
                    # OpenSearch's own field is literally "PaymentOption"; the
                    # others call the same concept "OfferingType".
                    "Payment Option": item.get("OfferingType") or item.get("PaymentOption"),
                    "Reservation Hours Used": utilization.get("TotalActualHours"),
                    "Utilization (%)": utilization.get("UtilizationPercentage"),
                    "Net Savings": utilization.get("NetRISavings"),
                    "Purchased Hours": utilization.get("PurchasedHours"),
                    "Number of Reservations": (
                        item.get("InstanceCount") or item.get("DBInstanceCount")
                        or item.get("CacheNodeCount") or item.get("NodeCount")
                    ),
                    "Reservation Hours Unused": utilization.get("UnusedHours"),
                    "Start Date": start,
                    "Expiry Date": end,
                    "Status": item.get("State"),
                    "Reservation ID": reservation_id,
                    "Lease ID": item.get("LeaseId"),
                    "Currency": item.get("CurrencyCode"),
                    "Fixed Price": item.get("FixedPrice"),
                    "Hourly Price": item.get("UsagePrice"),
                })
        except Exception as e:
            record_api_error(diagnostics, f"{label} RI CURRENT RESERVATION ERROR", e, action_name=f"{config['kind']}:current")
            rows.append(error_row(label, e))

    return rows


def build_ce_only_reservation_rows(utilization_records, matched_ids):
    """Reservations Cost Explorer reports utilization for (within the selected
    regions) but that no describe-reserved-* call returned — typically ones
    owned by a linked account in the organization, which these credentials'
    regional APIs can't see. Shown from CE's own attributes so they aren't
    silently missing from RI Current Reservation."""
    rows = []
    seen = set()
    for key, record in utilization_records.items():
        if key in matched_ids or id(record) in seen:
            continue
        seen.add(id(record))
        attributes = record["attributes"]
        utilization = record["utilization"]
        rows.append({
            "Resource Type": record["label"],
            "Reservation SKU": attributes.get("instanceType"),
            "Region": attributes.get("region"),
            "Payment Option": None,
            "Reservation Hours Used": utilization.get("TotalActualHours"),
            "Utilization (%)": utilization.get("UtilizationPercentage"),
            "Net Savings": utilization.get("NetRISavings"),
            "Purchased Hours": utilization.get("PurchasedHours"),
            "Number of Reservations": attributes.get("numberOfInstances"),
            "Reservation Hours Unused": utilization.get("UnusedHours"),
            "Start Date": attributes.get("startDateTime"),
            "Expiry Date": attributes.get("endDateTime"),
            "Status": attributes.get("status"),
            "Reservation ID": attributes.get("leaseId") or attributes.get("subscriptionId"),
            "Account ID": attributes.get("accountId"),
            "Source": "Cost Explorer (not returned by describe APIs — likely a linked account)",
        })
    return rows


# ============================================================
# RI RECOMMENDATION
# ============================================================
def get_ri_recommendations(clients, diagnostics, resource_types=None, term_in_years="ONE_YEAR", payment_options=None):
    resource_types = normalize_resource_types(resource_types, RI_RESOURCE_MAP)
    payment_options = payment_options or ["NO_UPFRONT"]
    rows = []

    for resource in resource_types:
        config = RI_RESOURCE_MAP[resource]
        label = config["display"]

        for payment_option in payment_options:
            try:
                response = clients["ce"].get_reservation_purchase_recommendation(
                    Service=config["ce_service"],
                    LookbackPeriodInDays=LOOKBACK_PERIOD_DAYS,
                    TermInYears=term_in_years,
                    PaymentOption=payment_option,
                )
                # One recommendation ID per API call (not per row) — AWS
                # doesn't give RI recommendation details their own individual IDs.
                recommendation_id = response.get("Metadata", {}).get("RecommendationId")
                recommendations = response.get("Recommendations", [])
                details_seen = False

                for recommendation in recommendations:
                    scope = recommendation.get("AccountScope")
                    for detail in recommendation.get("RecommendationDetails", []):
                        details_seen = True
                        rows.append({
                            "Reservation Type": label,
                            **flatten_instance_details(detail.get("InstanceDetails")),
                            "Number Of Reservations": detail.get("RecommendedNumberOfInstancesToPurchase"),
                            "Look Back Period": format_lookback_period(LOOKBACK_PERIOD_DAYS),
                            "Term": format_term(term_in_years),
                            "Payment Option": format_payment_option(payment_option),
                            "Potential Savings": detail.get("EstimatedMonthlySavingsAmount"),
                            "Recommendation Id": recommendation_id,
                            "Scope": scope,
                            "Currency": detail.get("CurrencyCode"),
                            "Avg Utilization %": detail.get("AverageUtilization"),
                            "Estimated Monthly Savings %": detail.get("EstimatedMonthlySavingsPercentage"),
                            "Estimated Monthly On-Demand Cost": detail.get("EstimatedMonthlyOnDemandCost"),
                            "Upfront Cost": detail.get("UpfrontCost"),
                            "Monthly Recurring Cost": detail.get("RecurringStandardMonthlyCost"),
                            "Break-Even (Months)": detail.get("EstimatedBreakEvenInMonths"),
                        })

                if not details_seen:
                    rows.append(note_row(label, f"No recommendation available ({format_payment_option(payment_option)})"))
            except Exception as e:
                record_api_error(
                    diagnostics, f"{label} RI RECOMMENDATION ERROR", e,
                    action_name=f"ce:GetReservationPurchaseRecommendation:{label}:{payment_option}",
                )
                rows.append(error_row(label, e))

    return rows


# ============================================================
# SAVINGS PLANS CURRENT DATA
# ============================================================
def get_savings_plans_current(clients, diagnostics, resource_types=None, utilization_by_arn=None):
    selected = normalize_resource_types(resource_types, SP_RESOURCE_MAP)
    utilization_by_arn = utilization_by_arn or {}

    try:
        # states is passed explicitly (every value AWS defines) so an
        # undocumented default can never silently exclude some of them —
        # this report is meant to show a plan's full lifecycle, not just
        # whichever states happen to be the default.
        response = clients["savingsplans"].describe_savings_plans(states=ALL_SAVINGS_PLAN_STATES)
        savings_plans = response.get("savingsPlans", [])
    except Exception as e:
        record_api_error(diagnostics, "SAVINGS PLANS CURRENT DATA ERROR", e, action_name="savingsplans:DescribeSavingsPlans")
        return [error_row("Savings Plans", e)]

    if selected:
        # Savings Plans are scoped by `productTypes` (a list, e.g. ["EC2"] or
        # ["RDS", "ElastiCache"] for newer Database Savings Plans) — NOT
        # `productType`/`serviceCode` (neither field exists on this response;
        # matching against them always failed, so every plan was silently
        # dropped whenever a resource-type filter was active, regardless of
        # what plans actually existed). A plan with no productTypes recorded
        # is kept rather than hidden, since that's more likely a gap in this
        # particular field than "matches nothing".
        savings_plans = [
            plan
            for plan in savings_plans
            if not plan.get("productTypes") or any(pt.upper() in selected for pt in plan["productTypes"])
        ]

    rows = []
    for plan in savings_plans:
        utilization = utilization_by_arn.get(plan.get("savingsPlanArn"), {})
        rows.append({
            "Savings Plan Name": plan.get("description"),
            "Savings Plan ID": plan.get("savingsPlanId"),
            "Account ID": account_id_from_arn(plan.get("savingsPlanArn")),
            "Scope": None,  # not part of DescribeSavingsPlans' response — AWS doesn't expose it here
            "Plan Type": plan.get("savingsPlanType"),
            "Payment Option": plan.get("paymentOption"),
            "Commitment/hour": plan.get("commitment"),
            "Term": term_label_from_seconds(plan.get("termDurationInSeconds")),
            "Status": plan.get("state"),
            "Start Date": plan.get("start"),
            "End Date": plan.get("end"),
            "Upfront Cost": plan.get("upfrontPaymentAmount"),
            "Utilization": utilization.get("UtilizationPercentage"),
            "Currency": plan.get("currency"),
            "Instance Family": plan.get("ec2InstanceFamily"),
            "Product Types": ", ".join(plan.get("productTypes") or []),
            "Region": plan.get("region"),
            "Recurring Payment": plan.get("recurringPaymentAmount"),
        })
    return rows


# ============================================================
# SAVINGS PLAN RECOMMENDATION
# ============================================================
def get_savings_plan_recommendations(clients, diagnostics, resource_types=None, term_in_years="ONE_YEAR", payment_options=None):
    resource_types = normalize_resource_types(resource_types, SP_RESOURCE_MAP)
    payment_options = payment_options or ["NO_UPFRONT"]
    rows = []

    for resource in resource_types:
        config = SP_RESOURCE_MAP[resource]
        label = config["display"]
        savings_plans_type = SP_TYPE_BY_RESOURCE.get(resource, "COMPUTE_SP")

        for payment_option in payment_options:
            try:
                response = clients["ce"].get_savings_plans_purchase_recommendation(
                    SavingsPlansType=savings_plans_type,
                    TermInYears=term_in_years,
                    PaymentOption=payment_option,
                    LookbackPeriodInDays=LOOKBACK_PERIOD_DAYS,
                )
                recommendation = response.get("SavingsPlansPurchaseRecommendation", {})
                details = recommendation.get("SavingsPlansPurchaseRecommendationDetails", [])
                scope = recommendation.get("AccountScope")

                if not details:
                    rows.append(note_row(label, f"No recommendation available ({format_payment_option(payment_option)})"))
                    continue

                for detail in details:
                    rows.append({
                        "Recommendation ID": detail.get("RecommendationDetailId"),
                        "Plan Type": savings_plans_type,
                        "Scope": scope,
                        "Look Back Period": format_lookback_period(LOOKBACK_PERIOD_DAYS),
                        "Term": format_term(term_in_years),
                        "Payment Option": format_payment_option(payment_option),
                        "Commitment/hour": detail.get("HourlyCommitmentToPurchase"),
                        "Estimated Savings (%)": detail.get("EstimatedSavingsPercentage"),
                        "Potential Savings (Month)": detail.get("EstimatedMonthlySavingsAmount"),
                        "Utilization": detail.get("EstimatedAverageUtilization"),
                        "Before Recommendation Purchase": detail.get("EstimatedOnDemandCost"),
                        "After Recommendation Purchase": detail.get("EstimatedSPCost"),
                        "Currency": detail.get("CurrencyCode"),
                        **flatten_savings_plan_details(detail.get("SavingsPlansDetails")),
                        "Resource Type": label,
                        "Upfront Cost": detail.get("UpfrontCost"),
                    })
            except Exception as e:
                record_api_error(
                    diagnostics, f"{label} SAVINGS PLAN RECOMMENDATION ERROR", e,
                    action_name=f"ce:GetSavingsPlansPurchaseRecommendation:{label}:{payment_option}",
                )
                rows.append(error_row(label, e))

    return rows


# ============================================================
# SAVINGS PLAN UTILIZATION
# ============================================================
def get_savings_plan_utilization(clients, diagnostics, start_date=None, end_date=None, data_types=None):
    if start_date is None or end_date is None:
        start_date, end_date = get_current_month_window()
    if data_types is None:
        data_types = ["ATTRIBUTES", "UTILIZATION", "SAVINGS", "AMORTIZED_COMMITMENT"]

    try:
        # Unlike RI utilization, this API doesn't support filtering by SERVICE
        # (AWS rejects it — allowed dimensions are LINKED_ACCOUNT,
        # SAVINGS_PLAN_ARN, SAVINGS_PLANS_TYPE, REGION, PAYMENT_OPTION,
        # INSTANCE_TYPE_FAMILY, AGREEMENT_END_DATE_TIME_*), so this is one
        # call covering every Savings Plan rather than one per resource type.
        # It's already broken down per individual plan (SavingsPlanArn), not
        # aggregated, so no further grouping is needed here.
        response = clients["ce"].get_savings_plans_utilization_details(
            TimePeriod={"Start": start_date, "End": end_date},
            DataType=data_types,
        )
        details = response.get("SavingsPlansUtilizationDetails", [])
    except Exception as e:
        record_api_error(diagnostics, "SAVINGS PLAN UTILIZATION ERROR", e, action_name="ce:GetSavingsPlansUtilizationDetails")
        return [error_row("Savings Plans", e)], {}

    rows = []
    by_arn = {}
    for item in details:
        # Attributes is a loosely-typed string map whose exact key casing
        # isn't nailed down in AWS's docs — check a couple of plausible
        # variants rather than betting on one.
        attributes = item.get("Attributes") or {}
        region = attributes.get("region") or attributes.get("REGION") or attributes.get("Region")
        instance_family = attributes.get("instanceFamily") or attributes.get("INSTANCE_FAMILY") or attributes.get("InstanceFamily")
        utilization = item.get("Utilization") or {}
        savings = item.get("Savings") or {}
        arn = item.get("SavingsPlanArn")

        rows.append({
            "Savings Plan ID": savings_plan_id_from_arn(arn),
            "Savings Plan ARN": arn,
            "Region": region,
            "Instance Family": instance_family,
            "Total Commitment": utilization.get("TotalCommitment"),
            "Used Commitment": utilization.get("UsedCommitment"),
            "Unused Commitment": utilization.get("UnusedCommitment"),
            "Utilization (%)": utilization.get("UtilizationPercentage"),
            "Net Savings": savings.get("NetSavings"),
            "On-Demand Cost Equivalent": savings.get("OnDemandCostEquivalent"),
        })
        if arn:
            by_arn[arn] = utilization
    return rows, by_arn


# ============================================================
# SAVINGS PLAN COVERAGE
# ============================================================
def get_savings_plan_coverage(clients, diagnostics, resource_types=None, start_date=None, end_date=None):
    resource_types = normalize_resource_types(resource_types, SP_RESOURCE_MAP)
    rows = []

    if start_date is None or end_date is None:
        start_date, end_date = get_current_month_window()

    for resource in resource_types:
        config = SP_RESOURCE_MAP[resource]
        label = config["display"]

        try:
            response = clients["ce"].get_savings_plans_coverage(
                TimePeriod={"Start": start_date, "End": end_date},
                Filter={"Dimensions": {"Key": "SERVICE", "Values": [config["ce_service"]]}},
            )
            for item in response.get("SavingsPlansCoverages", []):
                time_period = item.get("TimePeriod", {})
                coverage = item.get("Coverage", {})
                rows.append({
                    "Resource Type": label,
                    "Period Start": time_period.get("Start"),
                    "Period End": time_period.get("End"),
                    "Coverage %": coverage.get("CoveragePercentage"),
                    "Spend Covered by Savings Plans": coverage.get("SpendCoveredBySavingsPlans"),
                    "On-Demand Cost": coverage.get("OnDemandCost"),
                    "Total Cost": coverage.get("TotalCost"),
                })
        except Exception as e:
            if is_data_unavailable(e):
                # Expected when there's simply no Savings Plan coverage data
                # for this service/time range yet (e.g. no active plans) —
                # not a permission or API problem, so it isn't logged as one.
                continue
            record_api_error(diagnostics, f"{label} SAVINGS PLAN COVERAGE ERROR", e, action_name=f"ce:GetSavingsPlansCoverage:{label}")
            rows.append(error_row(label, e))

    return rows


# ============================================================
# EXECUTION
# ============================================================
def build_regional_clients(session, region_name):
    """The 5 clients whose data is genuinely scoped to one region — used
    once per region selected for RI Current Reservation."""
    return {
        "ec2": session.client("ec2", region_name=region_name),
        "rds": session.client("rds", region_name=region_name),
        "elasticache": session.client("elasticache", region_name=region_name),
        "redshift": session.client("redshift", region_name=region_name),
        "opensearch": session.client("opensearch", region_name=region_name),
    }


def get_reservation_and_savings_plans_report(
    access_key,
    secret_key,
    session_token,
    region_names=None,
    service_types=None,
    resource_types=None,
    term_in_years="ONE_YEAR",
    payment_options=None,
    granularity="MONTHLY",  # noqa: kept for API compatibility — see note below
    start_date=None,
    end_date=None,
    progress_callback=None,
):
    # `granularity` is accepted but no longer used: RI Utilization now groups
    # by individual reservation (GroupBy=SUBSCRIPTION_ID) instead of
    # aggregating across a resource type, and AWS's GetReservationUtilization
    # doesn't allow GroupBy and Granularity together. The parameter stays so
    # existing callers/requests don't break; it's just a no-op now.
    if resource_types is None:
        resource_types = ["EC2", "RDS", "ELASTICACHE"]
    if not region_names:
        region_names = ["us-east-1"]
    if not payment_options:
        payment_options = ["NO_UPFRONT"]
    selected_service_types = normalize_service_types(service_types)

    session = boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        aws_session_token=session_token,
    )

    # Cost Explorer and Savings Plans aren't partitioned by region at all —
    # one shared client (using whichever region happens to be first) covers
    # every section except RI Current Reservation, regardless of how many
    # regions were selected.
    clients = {
        "ce": session.client("ce", region_name=region_names[0]),
        "savingsplans": session.client("savingsplans", region_name=region_names[0]),
    }

    # Per-call diagnostics, kept local to this invocation (not a module-level
    # global) so concurrent API requests never mix each other's results.
    diagnostics = []

    total_steps = len(selected_service_types)
    completed_steps = 0

    def tick():
        nonlocal completed_steps
        completed_steps += 1
        if progress_callback:
            progress_callback(completed_steps, total_steps)

    result = {}

    # RI Current Reservation is enriched with per-reservation utilization, so
    # that utilization is fetched whenever either section is selected —
    # exactly once, shared between them. It's account-wide regardless of
    # region, unlike the reservation lookups below, so no region loop here.
    need_ri_utilization = "ri_current_reservation" in selected_service_types or "ri_utilization" in selected_service_types
    ri_utilization_rows, ri_utilization_records = ([], {})
    if need_ri_utilization:
        ri_utilization_rows, ri_utilization_records = get_ri_utilization_by_reservation(
            clients, diagnostics, resource_types, start_date=start_date, end_date=end_date, region_names=region_names
        )

    if "ri_current_reservation" in selected_service_types:
        # The only region-scoped section — run once per selected region and
        # combine, tagging each row with the region it actually came from.
        ri_current_rows = []
        matched_ids = set()
        for region_name in region_names:
            regional_clients = {**clients, **build_regional_clients(session, region_name)}
            ri_current_rows.extend(get_ri_current_reservations(
                regional_clients, diagnostics, resource_types, region_name=region_name,
                utilization_records=ri_utilization_records, matched_ids=matched_ids,
            ))
        ri_current_rows.extend(build_ce_only_reservation_rows(ri_utilization_records, matched_ids))
        result["ri_current_reservation"] = ri_current_rows
        tick()
    if "ri_recommendations" in selected_service_types:
        result["ri_recommendations"] = get_ri_recommendations(clients, diagnostics, resource_types, term_in_years, payment_options)
        tick()
    if "ri_utilization" in selected_service_types:
        result["ri_utilization"] = ri_utilization_rows
        tick()

    # Same sharing for Savings Plans Current, enriched with per-plan utilization.
    need_sp_utilization = "savings_plans_current" in selected_service_types or "savings_plan_utilization" in selected_service_types
    sp_utilization_rows, sp_utilization_by_arn = ([], {})
    if need_sp_utilization:
        sp_utilization_rows, sp_utilization_by_arn = get_savings_plan_utilization(
            clients, diagnostics, start_date=start_date, end_date=end_date
        )

    if "savings_plans_current" in selected_service_types:
        result["savings_plans_current"] = get_savings_plans_current(
            clients, diagnostics, resource_types, utilization_by_arn=sp_utilization_by_arn
        )
        tick()
    if "savings_plan_recommendations" in selected_service_types:
        result["savings_plan_recommendations"] = get_savings_plan_recommendations(
            clients, diagnostics, resource_types, term_in_years=term_in_years, payment_options=payment_options
        )
        tick()
    if "savings_plan_utilization" in selected_service_types:
        result["savings_plan_utilization"] = sp_utilization_rows
        tick()
    if "savings_plan_coverage" in selected_service_types:
        result["savings_plan_coverage"] = get_savings_plan_coverage(
            clients, diagnostics, resource_types, start_date=start_date, end_date=end_date
        )
        tick()

    result["diagnostics"] = diagnostics
    result["legend"] = LEGEND
    return result
