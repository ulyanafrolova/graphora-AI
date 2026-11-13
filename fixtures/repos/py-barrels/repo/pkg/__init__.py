from .auth import AuthService
from .server import create_server as make_server
from .tools import *
from .config import LIMIT
from .missing import nothing
from . import server

def version():
    return "1"
