import asyncio  # isort:skip
import sys  # isort:skip

from twisted.internet import asyncioreactor  # isort:skip

if "twisted.internet.reactor" not in sys.modules:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncioreactor.install(loop)

import importlib


from zope.interface import implementer

from twisted.application.service import IServiceMaker, MultiService, Service
from twisted.internet import defer, endpoints, reactor, threads
from twisted.plugin import IPlugin
from twisted.python import usage
from twisted.web import server
from txasgiresource import ASGIResource


class Options(usage.Options):

    optParameters = [
        ["application", "a", None, "Application"],
        [
            "description",
            "d",
            "tcp:8000:interface=127.0.0.1",
            "Twisted server description",
        ],
        [
            "proxy_headers",
            "p",
            False,
            "Parse proxy header and use them to replace client ip",
        ],
    ]


class ASGIService(Service):
    def __init__(self, resource, description):
        self.resource = resource
        self.description = description

    @defer.inlineCallbacks
    def startService(self):
        self.endpoint = yield endpoints.serverFromString(reactor, self.description)
        self.endpoint.listen(server.Site(self.resource))

    def stopService(self):
        self.resource.stop()


@implementer(IServiceMaker, IPlugin)
class ServiceMaker(object):
    tapname = "txasgi"
    description = "ASGI Server"
    options = Options

    def makeService(self, options):
        asyncio.set_event_loop(reactor._asyncioEventloop)

        module, function = options["application"].split(":")
        application = getattr(importlib.import_module(module), function)

        ms = MultiService()

        resource = ASGIResource(application, use_proxy_headers=options["proxy_headers"])
        ms.addService(ASGIService(resource, options["description"]))

        return ms


txasgi = ServiceMaker()
