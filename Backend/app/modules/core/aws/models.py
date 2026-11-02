from typing import Optional

from pydantic import BaseModel


class RolePermissionsRequest(BaseModel):
    access_key: str
    secret_key: str
    session_token: str
    role_name: str


class GenerateAccessKeyRequest(BaseModel):
    role_arn: str
    # Optional: generated automatically when not supplied (see
    # Generate_access_key_and_secret_key.default_role_session_name).
    role_session_name: Optional[str] = None
    external_id: Optional[str] = None



class AwsConfigRulesInventoryAcrossAllRegionsRequest(BaseModel):
    access_key: str
    secret_key: str
    session_token: str
