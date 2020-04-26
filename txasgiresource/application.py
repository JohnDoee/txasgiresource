import asyncio
from concurrent.futures import CancelledError

from twisted.internet import defer


class ApplicationManager:
    def __init__(self, application):
        self.application = application
        self.application_instances = {}

    @defer.inlineCallbacks
    def stop(self):
        wait_for = []
        for protocol in list(self.application_instances.keys()):
            promise = protocol.do_cleanup()
            if promise:
                wait_for.append(promise)

        for d in wait_for:
            yield defer.Deferred.fromFuture(d)

    def create_application_instance(self, protocol, scope):
        async def handle_reply(msg):
            protocol.handle_reply(msg)

        queue = asyncio.Queue()

        self.application_instances[protocol] = asyncio.ensure_future(
            self.application(scope=scope, receive=queue.get, send=handle_reply)
        )

        return queue

    def finish_protocol(self, protocol):
        wait_for = None
        if protocol in self.application_instances:
            if not self.application_instances[protocol].done():
                if not self.application_instances[protocol].cancelled():

                    def handle_cancel_exception(f):
                        try:
                            f.exception()
                        except CancelledError:
                            pass

                    self.application_instances[protocol].add_done_callback(
                        handle_cancel_exception
                    )
                    self.application_instances[protocol].cancel()
                wait_for = self.application_instances[protocol]
            del self.application_instances[protocol]
        return wait_for
