from app import execution
from app.modules.settings.models import CreateUserGroupRequest
from app.modules.settings.scripts.Create_user_groups import create_user_groups


class SettingsService:
    @staticmethod
    def stream_create_user_groups(request: CreateUserGroupRequest):
        def run(progress_callback):
            return create_user_groups(
                base_url=request.base_url,
                master_account_id=request.master_account_id,
                auth_token=request.auth_token,
                user_ids=request.user_ids,
                group_name=request.group_name,
                required_role_ids=request.required_role_ids,
                progress_callback=progress_callback,
            )

        return execution.stream(run)
