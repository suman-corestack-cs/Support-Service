from typing import List

from pydantic import BaseModel


class CreateUserGroupRequest(BaseModel):
    base_url: str
    master_account_id: str
    auth_token: str
    user_ids: List[str]
    group_name: str
    required_role_ids: List[str]
