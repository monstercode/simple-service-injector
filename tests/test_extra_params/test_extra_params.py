import pytest
import os
from service_provider.service_provider import ServiceProvider, ServiceArgumentsOrderError
from tests.test_extra_params.example_classes import NoParamsService, ExampleUserUpdaterService

def test_instanciate_with_extra_params():
    services = ServiceProvider(f"{os.path.dirname(__file__)}/services_allow_extra_params.yaml")
    example_user_service = services.get("example-user-updater", user_id=44, is_admin_user=True)
    assert isinstance(example_user_service.no_param_service, NoParamsService)
    assert example_user_service.user_id == 44
    assert example_user_service.is_admin_user
    isinstance(example_user_service, ExampleUserUpdaterService)


def test_instanciate_with_extra_arguments_raises_order_error():
    """When passing extra arguments at the instantiation time, the order of *args could be undefined
    In this example, the 'no_param_service' is a key word argument, but when passing the *args with the
    value 44, as the 'no_param_service' param is defined first, it tries would set the 44 to that param
    instead of setting the correct 'no_param_service'
    If the  ExampleUserUpdaterService.__init__ would reverse the order of the params, it would work. Like this

    class ExampleUserUpdaterService: # This works!
        def __init__(self, user_id: int, no_param_service, is_admin_user=False):

    instead of:

    class ExampleUserUpdaterService: # This doesn't because 44 should be assigned to no_param_service or user_id?
                                     # the actual problem is mixing the order of args and kwargs here
        def __init__(self, no_param_service, user_id: int, is_admin_user=False):


    """
    services = ServiceProvider(f"{os.path.dirname(__file__)}/services_allow_extra_params.yaml")
    with pytest.raises(ServiceArgumentsOrderError) as e:
        example_user_service = services.get("example-user-updater", 44, is_admin_user=True)
