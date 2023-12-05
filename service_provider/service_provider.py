import yaml
import os
import importlib


class DuplicatedServiceNameError(Exception):
    pass


class MissingConfigurationKeyError(Exception):
    pass


class MissingServiceClassError(Exception):
    pass


class UnknownConfigurationKeyError(Exception):
    pass


class UnknownServiceNameError(Exception):
    pass


class MaxDependencyDepthReachedError(Exception):
    pass


class ImportingObjectError(Exception):
    pass


class ServiceDefinitionNotFoundError(Exception):
    pass


class ServiceArgumentsOrderError(Exception):
    pass


class ServiceProvider:
    SERVICE_REFERENCE = "@"
    OBJECT_REFERENCE = "^"
    ENV_VAR_REFERENCE = "$"
    VALID_SERVICE_KEYS = {"class", "arguments", "named_arguments", "is_singleton"}

    MAX_DEPENDENCY_DEPTH = 100

    def __init__(self, *services_conf_paths):
        self.all_services_config = {}
        self.singleton_services = {}
        self.manually_set_services = {}
        self._load_services_from_yaml(*services_conf_paths)
        self._check_services_configuration()
        self._check_circular_dependencies()

    def _load_services_from_yaml(self, *services_conf_paths):
        services_conf_paths = list(set(services_conf_paths))

        for service_conf_path in services_conf_paths:
            with open(service_conf_path, "r") as fp:
                service_conf = yaml.full_load(fp.read())

                for service_name in service_conf:
                    service_conf[service_name]["__original_file_path"] = service_conf_path

                    if service_name in self.all_services_config:
                        raise DuplicatedServiceNameError(
                            f"Service {service_name} is defined twice in {service_conf_path} and {self.all_services_config[service_name]['__original_file_path']}"
                        )

                    self.all_services_config[service_name] = service_conf[service_name]

        for service_name in self.all_services_config:
            self.all_services_config[service_name].pop("__original_file_path")

    def _check_services_configuration(self):
        for service_name, service_config in self.all_services_config.items():
            if "class" not in service_config:
                raise MissingConfigurationKeyError("Missing 'class' key in service {service_name}")

            unknown_service_keys = set(service_config.keys()).difference(self.VALID_SERVICE_KEYS)
            if unknown_service_keys:
                raise UnknownConfigurationKeyError(
                    f"Unknown configuration keys '{unknown_service_keys}' for service {service_name}"
                )

    def _check_circular_dependencies(self):
        validated_services = dict()
        for service_name in self.all_services_config:
            validated_services[service_name] = False

        count = 0
        while not all(validated_services.values()):
            for service_name, config in self.all_services_config.items():
                # We first get all the dependencies
                all_service_dependencies = list(config.get("arguments", [])) + list(
                    config.get("named_arguments", {}).values())
                # Then we filter to get only the ones that are actual services and not objects or environment variables
                # We'll eventually reach services that don't depend upon other services, those will be marked as validated services
                # and the ones that depend on the just validated one will have that dependency validated as well.
                # Eventually, all dependencies will get validated
                services_dependencies = [
                    self._get_clean_service_name(dependency)
                    for dependency in all_service_dependencies
                    if dependency.startswith(self.SERVICE_REFERENCE) and not validated_services.get(
                        self._get_clean_service_name(dependency))
                ]

                # if we need to inject another service in this service, which is not defined, raise an exception
                for service_dependency_name in services_dependencies:
                    if service_dependency_name not in self.all_services_config:
                        raise UnknownServiceNameError(
                            f"Service '{service_name}' depends on unknown service '{service_dependency_name}''. Defined services are {self.get_all_services_names()}")

                validated_services[service_name] = len(services_dependencies) == 0
            count += 1

            # If after too many rounds we still have services that depends on other services that are
            #  not validated (because they depend on other services that need to be validated),
            #  we get to the conclusion that we are in a circular dependency case
            if count > self.MAX_DEPENDENCY_DEPTH:
                raise MaxDependencyDepthReachedError()

    def _instanciate_service(self, service_name, *extra_args, **extra_kwargs):
        # check if is singleton and if instanciated
        if self.all_services_config[service_name].get("is_singleton") and self.singleton_services[service_name]:
            return self.singleton_services[service_name]

        args_service_dependencies = self.all_services_config[service_name].get("arguments", [])
        arguments = [self._get_arg_value(arg, service_name) for arg in args_service_dependencies]

        kwargs = {
            key: self._get_arg_value(arg, service_name)
            for key, arg in self.all_services_config[service_name].get("named_arguments", {}).items()
        }

        if not extra_args:
            extra_args = ()
        if not extra_kwargs:
            extra_kwargs = {}

        try:
            clss = self._import_object(self.all_services_config[service_name]["class"])
        except ImportError:
            raise ImportingObjectError(
                f"Couldn't import the class {self.all_services_config[service_name]['class']} for service {service_name}"
            )

        try:
            instance = clss(*arguments, *extra_args, **kwargs, **extra_kwargs)
        except TypeError as e:
            if "__init__() got multiple values for argument" in e.args[0] and extra_args:
                error = f"""The extra arguments order is undefined behavior when service dependencies also are defined to use arguements insteado of named_arguments.
                If you are using extra arguments when instanciating the service, consider using key-word arguments.
                If you need to pass extra non-key arguments when instanciating the service, consider using named_arguments in the service definition
                original error {e}"""
                raise ServiceArgumentsOrderError(error)
            raise e

        if self.all_services_config[service_name].get("is_singleton", False):
            self.singleton_services[service_name] = instance

        return instance

    def _get_arg_value(self, arg: str, service_name):
        if arg.startswith(self.OBJECT_REFERENCE):
            try:
                return self._import_object(arg[1:])
            except ImportError as e:
                raise ImportingObjectError(f"Couldn't import object {arg} for service {service_name}")
        elif arg.startswith(self.ENV_VAR_REFERENCE):
            env_var = os.getenv(arg[1:])
            return env_var.strip('"').strip("'") if type(env_var) is str else env_var

        elif arg.startswith(self.SERVICE_REFERENCE):
            return self._instanciate_service(arg[1:])

        return arg

    def _import_object(self, path):
        splitted_path = path.split(".")
        module = importlib.import_module(".".join(splitted_path[:-1]))
        imported_object = getattr(module, splitted_path[-1])
        return imported_object

    def _get_clean_service_name(self, service_name):
        if service_name.startswith(self.SERVICE_REFERENCE):
            return service_name[1:].strip()
        return service_name

    def get(self, service_name, *extra_args, **extra_kwargs):
        if service_name in self.manually_set_services:
            return self.manually_set_services[service_name]

        if service_name not in self.all_services_config:
            raise ServiceDefinitionNotFoundError(f"Service '{service_name}' is not set in the configured services")

        return self._instanciate_service(service_name, *extra_args, **extra_kwargs)

    def get_all_services_names(self):
        return list(self.all_services_config.keys())

    def set(self, service_name, instance):
        self.manually_set_services[service_name] = instance
        return instance
