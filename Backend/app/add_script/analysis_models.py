from typing import List, Optional

from pydantic import BaseModel, Field

# Allowed values for a generated input's `type` — the exact same vocabulary
# ScriptPage.jsx's renderFieldControl already understands. "dynamic-select"
# and "async-select" aren't offered here: those depend on a specific
# loadOptions function wired up by hand in scriptsData.js (Mongo-backed
# dropdowns, region-URL lookups, ...), which an auto-generated script can't
# supply. Every parameter the script needs — including anything like a
# master account id, tenant id, or service account — is just a plain
# extra_inputs entry with one of these types, shown in the UI exactly as
# given, not swapped for a special dropdown chain.
ALLOWED_INPUT_TYPES = ["text", "number", "password", "select", "toggle", "list", "file", "date"]


class GeneratedInputOption(BaseModel):
    value: str
    label: str


class GeneratedInput(BaseModel):
    name: str = Field(..., description="Python parameter name the converted function accepts")
    label: str
    type: str
    required: bool = False
    default: Optional[object] = None
    description: Optional[str] = Field(None, description="Shown as an info-icon tooltip next to the label")
    options: Optional[List[GeneratedInputOption]] = Field(None, description="Only for type == 'select'")


class ScriptAnalysisResult(BaseModel):
    """The exact shape Claude is asked to return (as JSON) after analyzing
    the uploaded script(s), output sample, and description. Deliberately
    narrow: Claude converts the script's own logic and identifies its own
    parameters — the one well-established shared building block still
    attached automatically (the Generate Access & Secret Key panel) is
    requested here only as a boolean and assembled by file_writer.py from
    the same known-good code already used elsewhere, never regenerated.
    Everything else the script needs — including a master account id,
    tenant id, or any other CoreStack identifier — is just a plain input,
    shown in the UI exactly as given, not swapped for a dropdown chain."""

    summary: str = Field(..., description="One or two plain-English sentences describing what this script does")
    function_name: str = Field(..., description="snake_case name for the main entry-point function")
    converted_script_code: str = Field(
        ...,
        description=(
            "Full content of the new Python script file: the converted business logic as one main "
            "function (plus small helpers if needed), no print()/input(), no hardcoded credentials, "
            "returning a JSON-serializable dict. Accepts progress_callback=None and calls it during "
            "meaningful iteration if there's a natural per-item loop; omit it otherwise."
        ),
    )
    needs_generate_keys_panel: bool = Field(
        False,
        description=(
            "True if the script needs AWS access_key/secret_key/session_token to call AWS APIs. If true, "
            "still add access_key/secret_key/session_token as your own extra_inputs (type password, "
            "required) exactly as an already-converted script like Get_role_permission.py does — this flag "
            "only additionally attaches the existing 'Generate Access & Secret Key' companion panel so "
            "those 3 fields can be filled automatically instead of pasted in by hand."
        ),
    )
    needs_azure_secret_panel: bool = Field(
        False,
        description=(
            "True if the script authenticates to Azure with a service principal (tenant id, application/"
            "client id, application/client secret). Attaches the existing 'Decrypt Secret Key' companion "
            "panel, which decrypts a CoreStack Azure cloud account's stored secret and fills those fields in."
        ),
    )
    extra_inputs: List[GeneratedInput] = Field(
        default_factory=list,
        description="Every other parameter the converted function needs, in the order they should appear in the form",
    )
    outputs_description: str = Field(..., description="One sentence describing the shape of the returned result")
