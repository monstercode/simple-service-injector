import os

import pytest

from service_provider.service_provider import ServiceProvider, CircularDependencyError


def test_circular_dependency():
    with pytest.raises(CircularDependencyError, match="Circular dependency detected"):
        ServiceProvider(f"{os.path.dirname(__file__)}/circular_dependency_services.yaml")