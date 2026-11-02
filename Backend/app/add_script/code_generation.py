import io
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.add_script.analysis_models import ScriptAnalysisResult

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_ENV_PATH)

MODEL = "claude-sonnet-5"
# This model thinks before answering by default, and that thinking counts
# against max_tokens. A cap of 8000 left no room for the JSON on bigger scripts
# (the whole converted script is embedded in it), so the response came back as
# thinking only with no text at all. Use a generous cap and stream the request
# so a cap this large doesn't trip the SDK's HTTP timeout.
MAX_TOKENS = 64000

# Two real, already-working conversions from this codebase, embedded as
# few-shot examples so the model imitates this project's actual house style
# instead of inventing its own — no print()/input(), a JSON-serializable
# return value, progress_callback for per-item loops, and every parameter
# (including CoreStack ids like a master account) declared as a plain,
# ordinary extra_inputs entry rather than a special dropdown.
_EXAMPLE_SIMPLE_SCRIPT = '''import boto3


def get_role_permissions(access_key, secret_key, session_token, role_name, progress_callback=None):
    try:
        iam_client = boto3.client(
            'iam',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token
        )

        attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)
        attached = attached_policies.get("AttachedPolicies", [])

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
'''

_EXAMPLE_PER_ITEM_LOOP_SCRIPT = '''import requests
import time


def create_tenant(tenant_name, api_url, auth_token, master_account_id):
    headers = {"accept": "application/json", "X-Auth-Token": auth_token, "Content-Type": "application/json"}
    payload = {"name": tenant_name, "account_id": master_account_id}
    try:
        response = requests.post(f"{api_url.rstrip('/')}/tenants", json=payload, headers=headers, timeout=30)
        if response.status_code in (200, 201):
            return {"tenant_name": tenant_name, "status": "success", "status_code": response.status_code}
        return {"tenant_name": tenant_name, "status": "failed", "status_code": response.status_code, "response": response.text}
    except requests.exceptions.RequestException as e:
        return {"tenant_name": tenant_name, "status": "error", "error": str(e)}


def bulk_tenant_creation(api_url, auth_token, master_account_id, tenant_names, request_delay_seconds=0.5, progress_callback=None):
    results = []
    total = len(tenant_names)
    for i, tenant_name in enumerate(tenant_names, start=1):
        results.append(create_tenant(tenant_name.strip(), api_url, auth_token, master_account_id))
        time.sleep(request_delay_seconds)
        if progress_callback:
            progress_callback(i, total)
    return {"results": results}
'''

# The most common shape of script this feature actually receives: a bunch of
# blank placeholder constants at the top (the author's own way of marking
# "fill this in before running"), used inside logic that also calls other,
# perfectly fixed endpoints that were never meant to become inputs. This
# example exists specifically to show that only the blank placeholders turn
# into parameters — everything else about the script's behavior, including
# other hardcoded URLs, is left completely alone.
_EXAMPLE_BLANK_PLACEHOLDER_SCRIPT_BEFORE = '''import boto3
import requests

ACCESS_KEY = ""
SECRET_KEY = ""
SESSION_TOKEN = ""
ROLE_ARN = ""

def assume_and_notify():
    sts_client = boto3.client(
        "sts",
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        aws_session_token=SESSION_TOKEN,
    )
    response = sts_client.assume_role(RoleArn=ROLE_ARN, RoleSessionName="added-script-session")
    creds = response["Credentials"]

    # Always the same internal endpoint — not something the person running
    # this ever picks, so it's NOT a blank placeholder and stays hardcoded.
    requests.post("https://internal.example.com/notify", json={"role_arn": ROLE_ARN, "status": "assumed"})

    print(creds)

assume_and_notify()
'''

_EXAMPLE_BLANK_PLACEHOLDER_SCRIPT_AFTER = '''import boto3
import requests


def assume_and_notify(access_key, secret_key, session_token, role_arn):
    try:
        sts_client = boto3.client(
            "sts",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
        )
        response = sts_client.assume_role(RoleArn=role_arn, RoleSessionName="added-script-session")
        creds = response["Credentials"]

        # Same fixed internal endpoint as the original script — untouched,
        # because it was never a blank placeholder.
        requests.post("https://internal.example.com/notify", json={"role_arn": role_arn, "status": "assumed"})

        return {
            "access_key_id": creds["AccessKeyId"],
            "secret_access_key": creds["SecretAccessKey"],
            "session_token": creds["SessionToken"],
        }
    except Exception as e:
        return {"error": str(e)}
'''

SYSTEM_PROMPT = f"""You convert a plain, standalone Python automation script into an API-ready function for an \
internal FastAPI tool, following this codebase's established conventions exactly.

How to find the script's inputs — read this carefully, it's the part most likely to go wrong:
The script itself tells you exactly what should become an input: a blank placeholder variable assigned at \
the top of the file — e.g. `ACCESS_KEY = ""`, `SECRET_KEY = ""`, `SESSION_TOKEN = ""`, `ROLE_NAME = ""`, \
`REGION_NAME = ''`, `ROLE_ARN = ""`. That blank assignment is the author's own way of marking "fill this in \
before running" — treat every one of them as exactly one input. A script commonly also contains OTHER \
hardcoded values and other API calls that are perfectly correct as given and were never meant to be \
user-editable (a fixed internal notification endpoint, a constant that isn't blank, a URL that's always the \
same regardless of who runs it) — leave those completely alone. Do not invent inputs beyond what the blank \
placeholders declare, and do not "clean up", parameterize, or otherwise rewrite any value or call that isn't \
one of them — a faithful, minimal conversion of exactly what's blank is what's wanted, not a redesign.

Rules for `converted_script_code` (the full new script file's content):
- No `print()`, no `input()`, no interactive prompts.
- Every blank placeholder variable becomes a function parameter with the same meaning, snake_cased (e.g. \
`ACCESS_KEY` → `access_key`, `ROLE_ARN` → `role_arn`), declared in `extra_inputs`. Replace every place in the \
script that reads the old constant with the new parameter — nothing else about the script's logic changes. \
This applies just as much to a CoreStack master account id, tenant id, or service/cloud account id if the \
script marks one as blank — it's a plain `extra_inputs` entry like anything else, never a special dropdown \
or database-backed picker; the UI shows every input as a plain field of its declared type.
- The main function returns one JSON-serializable dict (not None, not a bare list unless that's genuinely \
the whole result) — wrap the original script's output into a sensible dict shape.
- Catch exceptions the original script would have let crash the process and return {{"error": str(e)}} \
instead, matching the examples below.
- If there's a natural per-item loop (e.g. one iteration per row/account/resource), accept a keyword \
argument `progress_callback=None` and call `progress_callback(processed_count, total_count)` after each \
iteration — omit this entirely for scripts with no such loop.
- Keep imports at the top of the file, only import what's actually used.
- If `needs_generate_keys_panel` is true, the function must accept `access_key`, `secret_key`, and \
`session_token` as its own named parameters (used to build a boto3 session/client), on top of whatever \
`extra_inputs` you also declare for them.
- If the script authenticates to Azure with a service principal, set `needs_azure_secret_panel` to true and \
name those parameters exactly `tenant_id` (Azure AD tenant), `application_id` (app/client id), \
`application_secret` (client secret), and `subscription_id` if it takes a single subscription — that panel \
fills fields with these names automatically. (Common existing names `app_id`, `client_id`, `client_secret` \
are also understood, but prefer the ones above.)

Three real examples of already-converted scripts in this exact house style:

--- Example 1: a simple script, no per-item loop ---
```python
{_EXAMPLE_SIMPLE_SCRIPT}
```

--- Example 2: a script taking a master_account_id (just an ordinary parameter — see its extra_inputs \
entry below) and a per-item progress loop ---
```python
{_EXAMPLE_PER_ITEM_LOOP_SCRIPT}
```
Its `extra_inputs` would include: {{"name": "master_account_id", "label": "Master Account ID", "type": "text", \
"required": true, "description": "CoreStack master account id this tenant is created under"}}

--- Example 3: blank placeholder constants become parameters; the other hardcoded API call does NOT ---
Before (as uploaded):
```python
{_EXAMPLE_BLANK_PLACEHOLDER_SCRIPT_BEFORE}
```
After (`converted_script_code`):
```python
{_EXAMPLE_BLANK_PLACEHOLDER_SCRIPT_AFTER}
```
Notice `https://internal.example.com/notify` appears unchanged in both — it was never blank, so it's not an \
input. Only `ACCESS_KEY`/`SECRET_KEY`/`SESSION_TOKEN`/`ROLE_ARN` became parameters.

You will be given: a target script name, which product bundle and cloud it belongs to, the full source of \
one or more uploaded Python scripts to convert (merge them into one cohesive result if there's more than \
one), a real sample of the script's actual output, and the person's own description of the script — which \
may also include their suggestions for how the output should be *displayed* (e.g. "show this as a table \
sorted by size", "group by region", "this is really just a pass/fail summary, not a big table"). Treat that \
description as guidance for shaping `outputs_description` and the structure of the dict your converted \
function returns — e.g. if they ask for a table, return a flat list of row objects with the fields they \
care about most first; if they describe a grouped or summarized view, shape the returned dict that way \
instead of a flat dump. The output sample is your ground truth for what fields/values actually exist; the \
description is guidance for how to organize and present them, not a reason to invent data the sample \
doesn't support.

Respond with ONLY a single JSON object — no markdown code fences, no commentary before or after — matching \
exactly this shape:
{{
  "summary": "one or two plain-English sentences describing what this script does",
  "function_name": "snake_case_main_function_name",
  "converted_script_code": "the full new script file's source code, as a single string with real newlines",
  "needs_generate_keys_panel": true or false,
  "needs_azure_secret_panel": true or false,
  "extra_inputs": [
    {{"name": "python_param_name", "label": "Human Label", "type": "text|number|password|select|toggle|list|file|date", \
"required": true or false, "default": null, "description": "shown as an info tooltip", "options": null}}
  ],
  "outputs_description": "one sentence describing the shape of the returned dict"
}}

`extra_inputs` must cover every single parameter the converted function needs, with no exceptions — there is \
no automatically-added field anymore. If needs_generate_keys_panel is true, DO still list \
access_key/secret_key/session_token in extra_inputs (type "password", required true) — that flag only \
attaches a convenience panel elsewhere in the UI, it does not add those 3 fields for you. The same goes for \
needs_azure_secret_panel: still list tenant_id/application_id/application_secret (and subscription_id if \
used) in extra_inputs yourself, with application_secret as type "password". For "select" \
inputs, always provide "options" (a genuine small fixed list — don't use "select" for something like an \
account id that has no fixed set of values, use "text" instead). Use "date" (not "text") for any input that's \
a calendar date — a real date picker is shown for it instead of a plain text box; the function still receives \
it as a plain "YYYY-MM-DD" string, exactly like any hand-parsed date string today. Order extra_inputs the way they should \
appear in the form, credentials first."""


def _read_output_sample(filename, content_bytes):
    """Returns either a plain-text preview (str) or, for PDFs, a
    ready-to-send Anthropic "document" content block — whichever the model
    can make direct use of."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        import base64

        return {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(content_bytes).decode("ascii")},
        }
    if lower.endswith((".xlsx", ".xls", ".xlsm")):
        import openpyxl

        try:
            workbook = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
        except Exception:
            # openpyxl only reads the modern zip-based formats (.xlsx/.xlsm) —
            # a genuine legacy binary .xls (or a corrupt upload) lands here.
            # Don't let that crash the whole request; fall through with a
            # plain-text-decode attempt as a last resort, same as any other
            # unrecognized format below.
            try:
                return content_bytes.decode("utf-8", errors="replace")[:20000]
            except Exception:
                return f"({filename} is an Excel file in a format that couldn't be parsed for a text preview — analysis will rely on the script source and description alone.)"
        lines = []
        for sheet in workbook.worksheets[:3]:  # cap: a handful of sheets is plenty of signal
            lines.append(f"--- Sheet: {sheet.title} ---")
            for row in list(sheet.iter_rows(values_only=True))[:30]:  # cap rows for prompt size
                lines.append(", ".join("" if v is None else str(v) for v in row))
        return "\n".join(lines)
    # .txt/.csv/.tsv/anything else text-like
    try:
        return content_bytes.decode("utf-8", errors="replace")[:20000]
    except Exception:
        return "(binary output sample — could not be read as text)"


def _extract_json_object(raw_text):
    """Parses the model's reply as a JSON object, tolerating a markdown fence
    or stray prose around it despite the prompt asking for bare JSON.
    Returns the parsed dict, or None if no JSON object can be found."""
    candidates = [raw_text]
    if raw_text.startswith("```"):
        unfenced = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        if unfenced.rstrip().endswith("```"):
            unfenced = unfenced.rstrip().rsplit("```", 1)[0]
        candidates.append(unfenced.strip())
    # Fall back to the outermost {...} span — skips any text before/after it.
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw_text[start:end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def call_claude_for_json(*, system_prompt, user_content, feature_name):
    """Sends one request and returns the reply parsed as a JSON object (dict).
    Shared by Add Script and Edit Script. Raises RuntimeError with a clear
    message on any failure (missing API key, API error, refusal, truncated
    or empty reply, reply that isn't JSON)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"ANTHROPIC_API_KEY is not set in Backend/.env — add your Anthropic API key there to use {feature_name}."
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIError as e:
        raise RuntimeError(f"Anthropic API call failed: {e}")

    if response.stop_reason == "refusal":
        raise RuntimeError(
            "Claude declined to process this script. If it contains hardcoded secrets (keys, client "
            "secrets, passwords), replace them with blank placeholders like SECRET = \"\" and try again."
        )
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude ran out of output space before finishing — the script is too large to process in one go. "
            "Try splitting it into smaller scripts."
        )

    raw_text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not raw_text:
        raise RuntimeError(f"Claude returned no text (stop reason: {response.stop_reason}). Please try again.")

    parsed = _extract_json_object(raw_text)
    if parsed is None:
        raise RuntimeError(f"Claude's response wasn't valid JSON. Raw response started with: {raw_text[:300]!r}")
    return parsed


def analyze_and_convert_script(*, script_name, bundle, cloud, description, script_files, output_files):
    """`script_files`/`output_files` are lists of (filename, content_bytes) tuples.
    Calls the Anthropic API and returns a validated ScriptAnalysisResult.
    Raises RuntimeError with a clear message on any failure (missing API
    key, API error, malformed/invalid response)."""
    user_content = [
        {
            "type": "text",
            "text": (
                f"Script name: {script_name}\n"
                f"Bundle: {bundle}\n"
                f"Cloud: {cloud or '(none — this bundle has no cloud dimension)'}\n"
                f"Description of the script, and suggestions for how its output should be displayed:\n"
                f"{description or '(none given)'}\n"
            ),
        }
    ]

    for filename, content in script_files:
        try:
            source = content.decode("utf-8")
        except UnicodeDecodeError:
            raise RuntimeError(f"'{filename}' isn't a readable UTF-8 text file — is it really a .py script?")
        user_content.append({"type": "text", "text": f"--- Uploaded script: {filename} ---\n```python\n{source}\n```"})

    for filename, content in output_files:
        sample = _read_output_sample(filename, content)
        if isinstance(sample, dict):
            user_content.append({"type": "text", "text": f"--- Sample output file: {filename} (PDF, attached below) ---"})
            user_content.append(sample)
        else:
            user_content.append({"type": "text", "text": f"--- Sample output file: {filename} ---\n{sample}"})

    parsed = call_claude_for_json(system_prompt=SYSTEM_PROMPT, user_content=user_content, feature_name="Add Script")

    try:
        return ScriptAnalysisResult(**parsed)
    except Exception as e:
        raise RuntimeError(f"Claude's response didn't match the expected shape: {e}")
