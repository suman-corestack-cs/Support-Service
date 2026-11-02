from datetime import datetime, timezone

import boto3


def default_role_session_name():
    """STS requires a RoleSessionName (2-64 chars of [\\w+=,.@-]) but it's only
    a label — it shows up in the customer's CloudTrail as who assumed the
    role — so it's generated rather than typed in each time."""
    return f"corestack-support-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def generate_access_and_secret_key(
    aws_access_key_id,
    aws_secret_access_key,
    role_arn,
    role_session_name=None,
    external_id=None,
    region_name="us-east-1",
):
    try:
        role_session_name = role_session_name or default_role_session_name()
        sts_client = boto3.client(
            "sts",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name,
        )

        assume_role_kwargs = {
            "RoleArn": role_arn,
            "RoleSessionName": role_session_name,
        }
        if external_id:
            assume_role_kwargs["ExternalId"] = external_id

        response = sts_client.assume_role(**assume_role_kwargs)

        credentials = response["Credentials"]
        assumed_role_user = response.get("AssumedRoleUser", {})

        return {
            "access_key": credentials["AccessKeyId"],
            "secret_key": credentials["SecretAccessKey"],
            "session_token": credentials["SessionToken"],
            "expiration": credentials["Expiration"].isoformat(),
            "region": region_name,
            "role_arn": role_arn,
            "role_name": role_arn.rsplit("/", 1)[-1] if role_arn else None,
            "assumed_role_user": {
                "arn": assumed_role_user.get("Arn"),
                "assumed_role_id": assumed_role_user.get("AssumedRoleId"),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        return {"error": str(e)}
