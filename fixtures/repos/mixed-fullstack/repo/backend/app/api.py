import yaml
import requests
from backend.app import models


def handler():
    return yaml, requests, models

# Code under backend/ is usually written with backend/ as the root, which the resolver does not know.
from app import models as subproject_models
