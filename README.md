# Python Service Injection
A dependency injection lib for Python3 using YAML defined services. Use the service container to auto-instantiate your services and forget about having configuration variables all over your code and centralize all your services and their dependencies in single YAML files.

## How to use it
### First
Define a YAML file with the structure of your services and the required dependencies. It looks likes this:


````
simple-service:
  class: services.simple.SimpleService
  arguments:
   - $TEST_ENV
  named_arguments:
    param_two: ^tests.services.example_settings.example_object
    param_three: '@no-params-service'
    param_four: 'Oh baby this is hardcoded'

no-params-service:
  class: services.basics.NoParamsService
````
The high level `simple-service`is the service name. 

The key `class` defines the module of class to instantiate that service.

The keys `arguments` and `named_arguments` are the equivalent to the `*args` and `**kwargs` parameters respectively, which should be map to the `__init__` class parameters

An extra key `is_singleton` can be added to mark the service as a Singleton, and everytime the `get` method is called, the same instance is returned.

#### Defining the parameters injections:

```
$TEST_ENV                => Starts with $  then it's an environment variable
^settings.example_object => Starts with ^  then it's an object in a module
'@no-params-service'     => starts with '@ then it's another service

If no prefix is used, a hardcoded string is assumed as parameter
```

### Second

Define your class somewhere, like in a `services` folder. The example service calss would look like:

```
class SimpleService:

    def __init__(self, param_one, param_two, param_three, param_four):
        self.param_one = param_one
        self.param_two = param_two
        self.param_three = param_three
        self.param_four = param_four

```

Nothing magical here.

### Third

Load your services definitions and let the library work it's magic to grab all the dependencies needed to instanciate your service, like this:

```
services = ServiceProvider(f"{os.path.dirname(__file__)}/services.yaml")
simple_service = services.get("simple-service")
```
Now `simple_service` is an instance of the `SimpleService` class ready to use, without having to explicitly import all the required parameters to create the instance or hardcoding configurations in `__init__`.

Define it once in your app, and import the `service` object wherever you need it!

## Extra Features

### Multiple files definitions
Use multiple YAML files to keep your YAML files short and logically encapsulated
The service provider will merge your files and check for name clashing.

```
general_services = f"{os.path.dirname(__file__)}/app_services.yaml"
monitoring_services = f"{os.path.dirname(__file__)}/monitoring_services.yaml"

services = ServiceProvider(general_services, monitoring_services)
```

### Pass extra parameters on the go

If your service has some non-dynamic dependencies (like a third-party service that connects to an external server) and dynamic dependencies obtained at runtime (like an environment setting for that external service), you can pass those parameters to the service like this
```
user_manager = services.get("user-manager", environment="sales")
users = user_manger.get_all_users()
```
The above code would get the `users-manager` service, and as the `environment` parameter will be passed to the `__init__` method too.
