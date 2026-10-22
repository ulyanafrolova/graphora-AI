import importlib
import importlib as il
from importlib import import_module


def load(name, x):
    importlib.import_module(name)
    importlib.import_module("plugins.alpha")
    __import__("json")
    il.import_module(".rel")
    return import_module(f"plugins.{x}")
