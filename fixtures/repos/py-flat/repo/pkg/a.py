"""Module a."""

from .b import f


def helper(*args):
    return f(args)


class Service:
    def run(self):
        return helper()

    @staticmethod
    def stop():
        pass
