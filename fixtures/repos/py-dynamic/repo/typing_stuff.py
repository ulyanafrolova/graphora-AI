from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.alpha import Thing

try:
    import ujson as json
except ImportError:
    import json


def lazy():
    import csv

    return csv, json


def typed(t: "Thing") -> None:
    return None
