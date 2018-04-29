import sys

from twisted.internet import asyncioreactor  # isort:skip
if "twisted.internet.reactor" not in sys.modules:
    asyncioreactor.install()

try:
    from .asgiresource import ASGIResource # NOQA
except ImportError:
    pass

__version__ = '2.1.0'
