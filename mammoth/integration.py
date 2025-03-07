import kfp.dsl.executor
from kfp import dsl
import inspect
from typing import get_type_hints
from typing import Dict, List
import pickle
import yaml
import os
from mammoth import custom_kfp
import json


_default_python = "3.11"
_default_packages = ()  # appended to ["mammoth-commons"]


def _path(method):
    running_path = os.path.abspath(os.getcwd()).lower()
    method_path = os.path.abspath(inspect.getfile(method)).lower()
    assert method_path.startswith(running_path), f"Running path is not a super-path of the path of module {method.__name__}:\nRunning path : {running_path}\nModule path: {method_path}\nHOW TO FIX:-\n- If you are running tests, create a launch configuration from the top level of mammoth-commons.\n- If you are building, change the console's folder (CD) to the top directory of mammoth-commons."
    method_path = method_path[len(running_path) :]
    method_path = os.path.join(".", *method_path.split(os.sep)[:-1])
    return method_path


def _class_to_name(arg_type):
    return arg_type.__name__


def metric(namespace, version, python=_default_python, packages=_default_packages):
    def wrapper(method):
        # prepare the kfp wrapper given decorator arguments
        name = method.__name__  # will use this as the component id
        base_image = f"python:{python}-slim-bullseye"
        target_image = f"{namespace}/{name}:{version}"
        kfp_wrapper = lambda func: custom_kfp.custom_create_component_from_func(
            func,
            true_func=method,
            base_image=base_image,
            target_image=target_image,
            packages_to_install=["mammoth-commons"] + list(packages),
        )

        # find signature and check that we can obtain the integration type from the returned type
        signature = inspect.signature(method)
        return_type = signature.return_annotation
        if return_type is inspect.Signature.empty:
            raise Exception(f"The metric {name} must declare a return type")
        if not hasattr(return_type, "integration"):
            raise Exception(
                f"Missing static field in the return type of {name}: {return_type.__name__}.integration"
            )

        # keep type hint names, keeping default kwargs (these will be kwarg parameters)
        type_hints = get_type_hints(method)
        defaults = dict()
        input_types = list()
        for pname, parameter in signature.parameters.items():
            if (
                pname == "sensitive"
            ):  # do not consider the sensitive attributes for component types
                continue
            arg_type = type_hints.get(pname, parameter.annotation)
            if parameter.default is not inspect.Parameter.empty:  # ignore kwargs
                defaults[pname] = (
                    "None"
                    if parameter.default is None
                    else parameter.default
                )
                continue
            if pname not in ["dataset", "model"]:
                raise Exception(
                    "Only `dataset`, `model`, `sensitive` and keyword arguments are supported for metrics"
                )
            if arg_type is inspect.Signature.empty:
                raise Exception(
                    f"Add a type annotation in method {name} for the argument: {pname}"
                )
            input_types.append(_class_to_name(arg_type))
            # print(f"Argument: {pname}, Type: {arg_type.__name__}")
        if len(input_types) != 2:
            raise Exception(
                "Your metric should have both a `dataset` and `model` arguments"
            )

        # create component_metadata/{name}_meta.yaml
        metadata = {
            "id": name,
            "name": " ".join(name.split("_")),
            "description": method.__doc__,
            "parameter_info": "No parameters needed."
            if not defaults
            else "Some parameters are needed.",
            "component_type": "METRIC",
            "input_types": input_types,
            "parameter_default": defaults,
            "output_types": [],  # no kfp output, the data are exported when running the metric
        }
        if not os.path.exists(_path(method) + "/component_metadata/"):
            os.makedirs(_path(method) + "/component_metadata/")
        with open(f"{_path(method)}/component_metadata/{name}_meta.yaml", "w") as file:
            yaml.dump(metadata, file, sort_keys=False)

        exec_context = globals().copy()
        exec_context.update(locals())
        param_name = name+"__params"
        # create the kfp method to be wrapped
        exec(f"""
def kfp_method(
    model: dsl.Input[dsl.Model],
    dataset: dsl.Input[dsl.Dataset],
    output: dsl.Output[return_type.integration],
    sensitive: List[str],
    {param_name}: Dict[str, any] = defaults
):
    parameters = {param_name}
    """+"""
    with open(dataset.path, "rb") as f:
        dataset_instance = pickle.load(f)
    with open(model.path, "rb") as f:
        model_instance = pickle.load(f)
    parameters = {
        **defaults,
        **parameters,
    }  # insert missing defaults into parameters (TODO: maybe this is not needed)
    parameters = {
        k: None if isinstance(v, str) and v == "None" else v
        for k, v in parameters.items()
    }
    ret = method(dataset_instance, model_instance, sensitive, **parameters)
    assert isinstance(ret, return_type)
    ret.export(output)
        """, exec_context)

        kfp_method = exec_context["kfp_method"]

        # rename the kfp_method so that kfp will create an appropriate name for it
        kfp_method.__name__ = name
        kfp_method.__module__ = method.__module__
        kfp_method.__mammoth_wrapped__ = method
        # return the wrapped kfp method
        return kfp_wrapper(kfp_method)

    return wrapper


def loader(
    namespace, version, ltype=None, python=_default_packages, packages=_default_packages
):
    def wrapper(method, ltype):
        # prepare the kfp wrapper given decorator arguments
        name = method.__name__  # will use this as the component id
        if ltype is None:
            if "data" in name.lower():
                ltype = "LOADER_DATA"
                if "model" in name.lower():
                    raise Exception(
                        "You can't have both `data` and `model` as part of your loader's name when its return type is not explicitly declared."
                    )
            elif "model" in name.lower():
                ltype = "LOADER_MODEL"
            else:
                raise Exception(
                    "Either `data` or `model` should be part of your loader's name when its return type is not explicitly declared."
                )

        base_image = f"python:{python}-slim-bullseye"
        target_image = f"{namespace}/{name}:{version}"
        kfp_wrapper = lambda func: custom_kfp.custom_create_component_from_func(
            func,
            true_func=method,
            base_image=base_image,
            target_image=target_image,
            packages_to_install=["mammoth-commons"] + list(packages),
        )

        # find signature and check that we can obtain the integration type from the returned type
        signature = inspect.signature(method)
        return_type = signature.return_annotation
        if return_type is inspect.Signature.empty:
            raise Exception(f"The loader {name} must declare a return type")
        if not hasattr(return_type, "integration"):
            raise Exception(
                f"Missing static field in the return type of {name}: {return_type.__name__}.integration"
            )
        if return_type.integration is inspect.Signature.empty:
            raise Exception(
                f"The loader {name} must declare a return type which is type-hinted"
            )

        # keep type hint names, keeping default kwargs (these will be kwarg parameters)
        type_hints = get_type_hints(method)
        defaults = dict()
        #input_types = list()
        for pname, parameter in signature.parameters.items():
            arg_type = type_hints.get(pname, parameter.annotation)
            if parameter.default is not inspect.Parameter.empty:  # ignore kwargs
                defaults[pname] = (
                    "None"
                    if parameter.default is None
                    else parameter.default
                )
                continue
            raise Exception(
                f"Add both a type annotation and default value in method {name} for the argument: {pname}"
            )
            #input_types.append(_class_to_name(arg_type))
        #if len(input_types) != 1:
        #    raise Exception("Your loader should have a 'path' argument")

        # create component_metadata/{name}_meta.yaml
        metadata = {
            "id": name,
            "name": " ".join(name.split("_")),
            "description": method.__doc__,
            "parameter_info": "No parameters needed."
            if not defaults
            else "Some parameters are needed.",
            "component_type": ltype,
            "parameter_default": defaults,
            "input_types": [],  # input_types would just be ["str"] instead
            "output_types": [_class_to_name(return_type)],
        }
        if not os.path.exists(_path(method) + "/component_metadata/"):
            os.makedirs(_path(method) + "/component_metadata/")
        with open(f"{_path(method)}/component_metadata/{name}_meta.yaml", "w") as file:
            yaml.dump(metadata, file, sort_keys=False)
        param_name = name+"__params"
        exec_context = globals().copy()
        exec_context.update(locals())
        # create the kfp method to be wrapped
        exec(f"""
def kfp_method(
    output: dsl.Output[return_type.integration],
    {param_name}: Dict[str, any] = defaults,
) -> str:
    parameters = {param_name}
    """+"""
    parameters = {
        **defaults,
        **parameters,
    }  # insert missing defaults into parameters (TODO: maybe this is not needed)
    parameters = {
        k: None if isinstance(v, str) and v == "None" else v
        for k, v in parameters.items()
    }
    ret = method(**parameters)
    assert isinstance(ret, return_type)
    with open(output.path, "wb") as file:
        pickle.dump(ret, file)
    return output.path
        """, exec_context)
        kfp_method = exec_context["kfp_method"]
        # rename the kfp_method so that kfp will create an appropriate name for it
        kfp_method.__name__ = name
        kfp_method.__module__ = method.__module__
        kfp_method.__mammoth_wrapped__ = method

        # return the wrapped kfp method
        return kfp_wrapper(kfp_method)

    return lambda method: wrapper(
        method, ltype
    )  # this is the proper way to let wrapper know of ltype
