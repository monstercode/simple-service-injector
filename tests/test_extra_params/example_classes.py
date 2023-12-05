class ExampleUserUpdaterService:
    def __init__(self, no_param_service, user_id: int, is_admin_user=False):
        self.no_param_service = no_param_service
        self.user_id = user_id
        self.is_admin_user = is_admin_user


class NoParamsService:
    pass
