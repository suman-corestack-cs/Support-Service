import requests


def create_user_groups(base_url, master_account_id, auth_token, user_ids, group_name, required_role_ids, progress_callback=None):
    userids = set()
    userids.update(user_ids)

    required_role_names = set(required_role_ids)

    headers = {
        "accept": "application/json",
        "X-Auth-Token": auth_token,
        "Content-Type": "application/json"
    }

    # --------------------
    # 1. Fetch Tenants (MASTER ACCOUNT scoped)
    # --------------------
    tenants_url = f"{base_url}/v1/master_accounts/{master_account_id}/tenants"

    tenants_resp = requests.get(tenants_url, headers=headers)
    tenants_resp.raise_for_status()

    tenants_data = tenants_resp.json()

    if isinstance(tenants_data, list):
        tenant_ids = [t["id"] for t in tenants_data]
    elif isinstance(tenants_data, dict):
        tenant_ids = [t["id"] for t in tenants_data.get("data", [])]
    else:
        raise Exception("Unexpected tenants API response format")

    # --------------------
    # 2. Fetch Roles per Tenant
    # --------------------
    role_ids = set()
    all_roles_debug = []
    total_tenants = len(tenant_ids)

    for tenant_index, tenant_id in enumerate(tenant_ids, start=1):
        roles_url = f"{base_url}/tenants/{tenant_id}/roles"

        try:
            roles_resp = requests.get(roles_url, headers=headers)
            roles_resp.raise_for_status()

            roles_data = roles_resp.json()

            # Save debug info
            all_roles_debug.append({
                "tenant_id": tenant_id,
                "response": roles_data
            })

            # Extract roles from the "roles" array in response
            roles_list = roles_data.get("roles", [])

            # Match by role name
            for role in roles_list:
                role_id = role.get("id")
                role_name = role.get("name")

                if not role_id or not role_name:
                    continue

                if role_name in required_role_names:
                    role_ids.add(role_id)

        except requests.exceptions.RequestException:
            if progress_callback:
                progress_callback(tenant_index, total_tenants)
            continue

        if progress_callback:
            progress_callback(tenant_index, total_tenants)

    # --------------------
    # 3. SAFETY CHECK
    # --------------------
    if not role_ids:
        return {
            "error": (
                "No required roles found. "
                "Check the role names in required_role_ids or review tenant_roles below."
            ),
            "tenant_roles": all_roles_debug,
        }

    # --------------------
    # 4. Build Final Payload
    # --------------------
    final_payload = {
        "group_name": group_name,
        "tenant_ids": tenant_ids,
        "roles": list(role_ids),
        "users": list(userids)
    }

    # --------------------
    # 5. Send to User Groups API
    # --------------------
    user_groups_url = f"{base_url}/v2/user_groups"

    try:
        group_resp = requests.post(
            user_groups_url,
            headers=headers,
            json=final_payload
        )

        group_resp.raise_for_status()

        result = group_resp.json()

        return {"payload": final_payload, "response": result, "tenant_roles": all_roles_debug}

    except requests.exceptions.RequestException as e:
        error_detail = {"error": str(e)}
        if hasattr(e, 'response') and e.response is not None:
            error_detail["status_code"] = e.response.status_code
            error_detail["response"] = e.response.text
        return {"payload": final_payload, "error": error_detail, "tenant_roles": all_roles_debug}
