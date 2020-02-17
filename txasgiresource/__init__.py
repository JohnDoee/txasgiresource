import sys

from twisted.internet import asyncioreactor  # isort:skip
if "twisted.internet.reactor" not in sys.modules:
    asyncioreactor.install()

from .asgiresource import ASGIResource # NOQA

__version__ = '2.2.0'
