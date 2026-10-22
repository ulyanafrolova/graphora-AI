"""Entry point."""
import os
import requests
from pkg import a
from pkg.a import helper
import pkg.sub.deep


def run():
    return helper(os.getcwd(), a, requests, pkg)
