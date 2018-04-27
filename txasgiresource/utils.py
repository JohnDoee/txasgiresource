from twisted.internet import defer, reactor
from twisted.web import resource


def sleep(secs):
    d = defer.Deferred()
    return d, reactor.callLater(secs, d.callback, None)


def send_error_page(request, status, brief, detail):
    if not request.finished and request.channel:
        error_page = resource.ErrorPage(status, brief, detail).render(request)
        request.write(error_page)
        request.finish()
