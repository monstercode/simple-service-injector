import importlib
import os
import threading

import yaml


class DuplicatedServiceNameError(Exception):
    pass


class MissingConfigurationKeyError(Exception):
    pass


class MissingServiceClassError(Exception):
    pass


class UnknownConfigurationKeyError(Exception):
    pass


class InvalidConfigurationValueError(Exception):
    pass


class UnknownServiceNameError(Exception):
    pass


class MaxDependencyDepthReachedError(Exception):
    """Kept for backwards compatibility, see CircularDependencyError."""


class CircularDependencyError(MaxDependencyDepthReachedError):
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

    def __init__(self, *services_conf_paths):
        self.all_services_config = {}
        self.singleton_services = {}
        self.manually_set_services = {}
        # Reentrant because a singleton can depend on other singletons
        self._singleton_lock = threading.RLock()
        self._load_services_from_yaml(*services_conf_paths)
        self._check_services_configuration()
        self._check_circular_dependencies()

    # ------------------------------------------------------------------
    # Loading and validation
    # ------------------------------------------------------------------
    def _load_services_from_yaml(self, *services_conf_paths):
        origins = {}

        # dict.fromkeys removes duplicated paths but keeps the order
        for service_conf_path in dict.fromkeys(services_conf_paths):
            with open(service_conf_path, "r") as fp:
                service_conf = yaml.safe_load(fp) or {}

            if not isinstance(service_conf, dict):
                raise InvalidConfigurationValueError(
                    f"The file {service_conf_path} must contain a mapping of service names to definitions"
                )

            for service_name, definition in service_conf.items():
                if service_name in self.all_services_config:
                    raise DuplicatedServiceNameError(
                        f"Service {service_name} is defined twice in {service_conf_path} and {origins[service_name]}"
                    )

                # A service with an empty body is reported later as a missing 'class' key
                if definition is None:
                    definition = {}
                if not isinstance(definition, dict):
                    raise InvalidConfigurationValueError(
                        f"The definition of service {service_name} in {service_conf_path} must be a mapping"
                    )

                self.all_services_config[service_name] = definition
                origins[service_name] = service_conf_path

    def _check_services_configuration(self):
        for service_name, service_config in self.all_services_config.items():
            if "class" not in service_config:
                raise MissingConfigurationKeyError(f"Missing 'class' key in service {service_name}")

            unknown_service_keys = set(service_config.keys()).difference(self.VALID_SERVICE_KEYS)
            if unknown_service_keys:
                raise UnknownConfigurationKeyError(
                    f"Unknown configuration keys {sorted(unknown_service_keys)} for service {service_name}"
                )

            # Normalize optional keys so the rest of the code can rely on them
            arguments = service_config.get("arguments")
            if arguments is None:
                arguments = []
            if not isinstance(arguments, list):
                raise InvalidConfigurationValueError(f"'arguments' of service {service_name} must be a list")
            service_config["arguments"] = arguments

            named_arguments = service_config.get("named_arguments")
            if named_arguments is None:
                named_arguments = {}
            if not isinstance(named_arguments, dict):
                raise InvalidConfigurationValueError(f"'named_arguments' of service {service_name} must be a mapping")
            service_config["named_arguments"] = named_arguments

            service_config["is_singleton"] = self._parse_is_singleton(
                service_config.get("is_singleton", False), service_name
            )

    @staticmethod
    def _parse_is_singleton(value, service_name):
        if isinstance(value, bool):
            return value
        # Quoted values in YAML ('false') arrive as strings, which are always truthy
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return value.strip().lower() == "true"
        raise InvalidConfigurationValueError(
            f"'is_singleton' of service {service_name} must be true or false, got {value!r}"
        )

    def _is_service_reference(self, arg):
        return isinstance(arg, str) and arg.startswith(self.SERVICE_REFERENCE)

    def _get_service_dependencies(self, config):
        all_arguments = list(config["arguments"]) + list(config["named_arguments"].values())
        return [self._get_clean_service_name(arg) for arg in all_arguments if self._is_service_reference(arg)]

    def _check_circular_dependencies(self):
        graph = {}
        for service_name, config in self.all_services_config.items():
            dependencies = self._get_service_dependencies(config)
            for dependency in dependencies:
                if dependency not in self.all_services_config:
                    raise UnknownServiceNameError(
                        f"Service '{service_name}' depends on unknown service '{dependency}'. "
                        f"Defined services are {self.get_all_services_names()}"
                    )
            graph[service_name] = dependencies

        # Iterative depth-first search, so we can report the exact cycle
        done = set()
        for start in graph:
            if start in done:
                continue
            path = [start]
            on_path = {start}
            iterators = [iter(graph[start])]
            while iterators:
                try:
                    dependency = next(iterators[-1])
                except StopIteration:
                    iterators.pop()
                    finished = path.pop()
                    on_path.discard(finished)
                    done.add(finished)
                    continue

                if dependency in on_path:
                    cycle = path[path.index(dependency):] + [dependency]
                    raise CircularDependencyError("Circular dependency detected: " + " -> ".join(cycle))

                if dependency not in done:
                    path.append(dependency)
                    on_path.add(dependency)
                    iterators.append(iter(graph[dependency]))

    # ------------------------------------------------------------------
    # Instantiation
    # ------------------------------------------------------------------
    def _instanciate_service(self, service_name, *extra_args, **extra_kwargs):
        config = self.all_services_config[service_name]

        if not config["is_singleton"]:
            return self._build_service(service_name, extra_args, extra_kwargs)

        with self._singleton_lock:
            # 'in' instead of truthiness: an instance can legitimately be falsy
            if service_name not in self.singleton_services:
                self.singleton_services[service_name] = self._build_service(service_name, extra_args, extra_kwargs)
            return self.singleton_services[service_name]

    def _build_service(self, service_name, extra_args, extra_kwargs):
        config = self.all_services_config[service_name]

        arguments = [self._get_arg_value(arg, service_name) for arg in config["arguments"]]
        kwargs = {key: self._get_arg_value(arg, service_name) for key, arg in config["named_arguments"].items()}
        # Extra keyword arguments passed to get() win over the ones in the YAML
        kwargs.update(extra_kwargs)

        try:
            clss = self._import_object(config["class"])
        except (ImportError, AttributeError, ValueError) as e:
            raise ImportingObjectError(
                f"Couldn't import the class {config['class']} for service {service_name}"
            ) from e

        try:
            return clss(*arguments, *extra_args, **kwargs)
        except TypeError as e:
            if extra_args and "got multiple values for argument" in str(e):
                raise ServiceArgumentsOrderError(
                    "The order of extra positional arguments is undefined behavior when the service "
                    "dependencies are also defined with 'arguments' instead of 'named_arguments'. "
                    "When instantiating the service with extra arguments, prefer keyword arguments. "
                    "If you need extra positional arguments, use 'named_arguments' in the service definition. "
                    f"Original error: {e}"
                ) from e
            raise

    def _get_arg_value(self, arg, service_name):
        # YAML can give us ints, floats, bools, lists... those are passed as they are
        if not isinstance(arg, str):
            return arg

        if arg.startswith(self.OBJECT_REFERENCE):
            try:
                return self._import_object(arg[1:])
            except (ImportError, AttributeError, ValueError) as e:
                raise ImportingObjectError(f"Couldn't import object {arg} for service {service_name}") from e

        if arg.startswith(self.ENV_VAR_REFERENCE):
            env_var = os.getenv(arg[1:])
            if env_var is None:
                return None
            return env_var.strip('"').strip("'")

        if arg.startswith(self.SERVICE_REFERENCE):
            # Go through get() so manually set services are also injected
            return self.get(self._get_clean_service_name(arg))

        return arg

    def _import_object(self, path):
        module_path, _, object_name = path.rpartition(".")
        if not module_path:
            raise ValueError(f"'{path}' must have the form 'package.module.object'")
        module = importlib.import_module(module_path)
        return getattr(module, object_name)

    def _get_clean_service_name(self, service_name):
        if service_name.startswith(self.SERVICE_REFERENCE):
            return service_name[1:].strip()
        return service_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
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