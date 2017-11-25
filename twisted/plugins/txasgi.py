import importlib

from zope.interface import implementer

from twisted.application.service import IServiceMaker, Service, MultiService
from twisted.internet import endpoints, reactor, defer, threads
from twisted.plugin import IPlugin
from twisted.python import usage
from twisted.web import server

from txasgiresource import ASGIResource

class Options(usage.Options):

    optParameters = [
        ["channel_layer", "c", None, "Channel layer"],
        ["description", "d", "tcp:8000:interface=127.0.0.1", "Twisted server description"],
        ["workers", "w", "0", "Number of Channels workers"],
        ["proxy_headers", "p", False, "Parse proxy header and use them to replace client ip"],
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


class WorkerService(Service):
    def __init__(self, channel_layer, worker_count):
        self.channel_layer = channel_layer
        self.worker_count = worker_count
        self._workers = []

    def startService(self):
        from channels import DEFAULT_CHANNEL_LAYER, channel_layers
        from channels.staticfiles import StaticFilesConsumer
        from channels.worker import Worker

        reactor.suggestThreadPoolSize(self.worker_count + 3)

        channel_layer = channel_layers[DEFAULT_CHANNEL_LAYER]
        channel_layer.router.check_default(http_consumer=StaticFilesConsumer())
        for _ in range(self.worker_count):
            w = Worker(channel_layer, signal_handlers=False)
            self._workers.append((w, threads.deferToThread(w.run)))

    @defer.inlineCallbacks
    def stopService(self):
        for worker, thread in self._workers:
            worker.termed = True

        for worker, thread in self._workers:
            yield thread


@implementer(IServiceMaker, IPlugin)
class ServiceMaker(object):
    tapname = "txasgi"
    description = "ASGI Server"
    options = Options

    def makeService(self, options):
        module, function = options['channel_layer'].split(':')
        channel_layer = getattr(importlib.import_module(module), function)

        ms = MultiService()

        resource = ASGIResource(channel_layer)
        ms.addService(ASGIService(resource, options['description']))

        worker_count = int(options['workers'])
        if worker_count > 0:
            ms.addService(WorkerService(channel_layer, worker_count))

        return ms

txasgi = ServiceMaker()