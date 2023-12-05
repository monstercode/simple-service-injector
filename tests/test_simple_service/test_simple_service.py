import os
from service_provider.service_provider import ServiceProvider
from tests.test_simple_service.example_classes import SimpleService, NoParamsService

def test_simple_service():
    # set a test enrionment
    os.environ["PYTHON_SERVICE_PROVIDER_TEST_ENV"] = "This is a test env var"

    services = ServiceProvider(f"{os.path.dirname(__file__)}/test_services.yaml")
    assert set(services.get_all_services_names()) == set(["simple-service", "no-params-service"])

    simple_service = services.get("simple-service")
    assert isinstance(simple_service, SimpleService)
    assert simple_service.param_one == "This is a test env var"
    assert simple_service.param_two == ["1", "2", "3"]
    assert isinstance(simple_service.param_three, NoParamsService)

    no_params_service = services.get("no-params-service")
    assert isinstance(no_params_service, NoParamsService)

    os.environ.pop("PYTHON_SERVICE_PROVIDER_TEST_ENV")
