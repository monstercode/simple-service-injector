import pytest
import os
from service_provider.service_provider import ServiceProvider
from service_provider.service_provider import MaxDependencyDepthReachedError

def test_circular_dependency():
    with pytest.raises(MaxDependencyDepthReachedError):
        services = ServiceProvider(f"{os.path.dirname(__file__)}/circular_dependency_services.yaml")
