import boto3


def get_config_rules_all_regions(access_key, secret_key, session_token, progress_callback=None):
    try:
        session = boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token
        )

        regions = session.get_available_regions('config')

        config_rules = []
        total = len(regions)
        processed = 0

        for region in regions:
            client = session.client('config', region_name=region)

            try:
                response = client.describe_config_rules()

                for rule in response.get('ConfigRules', []):
                    config_rule_name = rule.get("ConfigRuleName", "N/A")
                    description = rule.get("Description", "N/A")
                    source = rule["Source"]["SourceIdentifier"] if "Source" in rule else "N/A"
                    input_parameters = rule.get("InputParameters", "N/A")
                    scope = ", ".join(
                        rule["Scope"]["ComplianceResourceTypes"]) if "Scope" in rule and "ComplianceResourceTypes" in rule[
                        "Scope"] else "N/A"

                    config_rules.append({
                        "region": region,
                        "config_rule_name": config_rule_name,
                        "description": description,
                        "source": source,
                        "input_parameters": input_parameters,
                        "scope": scope,
                    })

            except Exception:
                pass

            processed += 1
            if progress_callback:
                progress_callback(processed, total)

        return {
            "config_rules": config_rules,
            "total_count": len(config_rules),
        }

    except Exception as e:
        return {"error": str(e)}
