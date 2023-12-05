import os
import pytest
from service_provider.service_provider import ServiceProvider, DuplicatedServiceNameError

def test_multi_file_definitions():
    services = ServiceProvider(f"{os.path.dirname(__file__)}/services_part_one.yaml",f"{os.path.dirname(__file__)}/services_part_two.yaml",)
    assert set(services.get_all_services_names()) == set(["no-params-service-file-one", "no-params-service-file-two"])

def test_multi_file_definitions_clash_naming():
    with pytest.raises(DuplicatedServiceNameError) as e:
        services = ServiceProvider(f"{os.path.dirname(__file__)}/services_part_one.yaml",f"{os.path.dirname(__file__)}/services_part_one_repeated.yaml",)
        assert "Service no-params-service-file-one is defined twice" in e.value.args[0]
