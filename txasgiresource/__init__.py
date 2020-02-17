import sys

from .asgiresource import ASGIResource  # NOQA

from twisted.internet import asyncioreactor  # isort:skip

if "twisted.internet.reactor" not in sys.modules:
    asyncioreactor.install()


__version__ = "2.2.0"
