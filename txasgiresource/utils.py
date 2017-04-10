import random
import string

from twisted.internet import defer, reactor
from twisted.web import resource


def sleep(secs):
    d = defer.Deferred()
    return d, reactor.callLater(secs, d.callback, None)


class TimeoutException(Exception):
    pass


def timeout_defer(_timeout, d):
    combined_d = defer.Deferred()
    sleep_d, timer = sleep(_timeout)

    def timed_out(result):
        if not combined_d.called:
            combined_d.errback(TimeoutException())

    def failed(result):
        if timer.active():
            timer.cancel()

        if not combined_d.called:
            combined_d.errback(result)

    def successful(result):
        if timer.active():
            timer.cancel()

        if not combined_d.called:
            combined_d.callback(result)

    sleep_d.addCallback(timed_out)
    d.addCallback(successful)
    d.addErrback(failed)

    return combined_d


def send_error_page(request, status, brief, detail):
    error_page = resource.ErrorPage(status, brief, detail).render(request)
    request.write(error_page)
    request.finish()


def random_str(choices=string.ascii_letters, length=10):
    return "".join(random.choice(choices) for _ in range(length))
