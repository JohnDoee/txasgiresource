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
        for protocol, application_instance in list(self.application_instances.items()):
            if protocol.do_cleanup():
                wait_for.append(application_instance)

        for d in wait_for:
            try:
                yield defer.Deferred.fromFuture(d)
            except CancelledError:
                pass

    def create_application_instance(self, protocol, scope):
        async def handle_reply(msg):
            protocol.handle_reply(msg)

        queue = asyncio.Queue()

        self.application_instances[protocol] = asyncio.ensure_future(
            self.application(scope=scope, receive=queue.get, send=handle_reply)
        )

        return queue

    def finish_protocol(self, protocol):
        wait_for = False
        if protocol in self.application_instances:
            if not self.application_instances[protocol].done():
                if self.application_instances[protocol].cancel():

                    def handle_cancel_exception(f):
                        try:
                            f.exception()
                        except CancelledError:
                            pass

                    self.application_instances[protocol].add_done_callback(
                        handle_cancel_exception
                    )
                wait_for = True
            del self.application_instances[protocol]
        return wait_for
