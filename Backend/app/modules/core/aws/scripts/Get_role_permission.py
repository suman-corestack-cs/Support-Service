import boto3


def get_role_permissions(access_key, secret_key, session_token, role_name, progress_callback=None):
    try:
        # Create IAM client with provided credentials
        iam_client = boto3.client(
            'iam',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token
        )

        # Get the attached policies for the role
        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)
        attached = attached_policies.get("AttachedPolicies", [])

        # Get inline policies for the role
        inline_policies = iam_client.list_role_policies(RoleName=role_name)
        inline_names = inline_policies.get("PolicyNames", [])

        total = len(attached) + len(inline_names)
        processed = 0

        attached_policies_list = []
        for policy in attached:
            attached_policies_list.append({
                "policy_name": policy["PolicyName"],
                "policy_arn": policy["PolicyArn"],
            })
            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        inline_policies_list = []
        for policy_name in inline_names:
            policy_details = iam_client.get_role_policy(RoleName=role_name, PolicyName=policy_name)
            inline_policies_list.append({
                "policy_name": policy_name,
                "policy_document": policy_details["PolicyDocument"],
            })
            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        return {
            "attached_policies": attached_policies_list,
            "inline_policies": inline_policies_list,
        }

    except Exception as e:
        return {"error": str(e)}
