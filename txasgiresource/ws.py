import logging

from autobahn.twisted.websocket import ConnectionDeny, WebSocketServerFactory, WebSocketServerProtocol

from twisted.internet import defer
from twisted.protocols import policies

logger = logging.getLogger(__name__)


class ASGIWebSocketServerProtocol(WebSocketServerProtocol, policies.TimeoutMixin):
    accepted = False
    opened = False
    accept_promise = None
    queue = None

    @defer.inlineCallbacks
    def _onConnect(self, request):
        scope = dict(self.factory.base_scope)
        scope['type'] = 'websocket'
        scope['scheme'] = 'ws%s' % (scope.pop('_ssl'))
        # TODO: add subprotocols

        try:
            self.queue = yield self.factory.application.create_application_instance(self, scope)
            self.opened = True
        except Exception as e:
            logger.exception('Failed to create application')
            self.reply_defer.callback({'type': 'websocket.close'})
        else:
            self.queue.put_nowait({'type': 'websocket.connect'})

        self.send_replies()

    def onConnect(self, request):
        self.request = request
        self.setTimeout(self.factory.idle_timeout)
        self.accept_promise = defer.Deferred()
        self.reply_defer = defer.Deferred()

        self._onConnect(request)

        return self.accept_promise

    @defer.inlineCallbacks
    def send_replies(self):
        while True:
            try:
                reply = yield self.reply_defer
            except defer.TimeoutError:
                logger.debug('We hit a timeout')
                self.dropConnection(abort=True)
                break
            except defer.CancelledError:
                self.dropConnection(abort=True)
                break

            if not self.accepted:
                if reply['type'] == 'websocket.accept':
                    logger.debug('Accepting websocket connection')
                    self.accepted = True
                    self.accept_promise.callback(None)
                elif reply['type'] == 'websocket.close':
                    self.accept_promise.errback(ConnectionDeny(code=403, reason="Denied"))
                    self.dropConnection(abort=True)
                    break
                else:
                    continue

            if reply['type'] == 'websocket.send':
                if reply.get('binary') is not None:
                    self.sendMessage(reply['binary'], True)

                if reply.get('text') is not None:
                    self.sendMessage(reply['text'].encode('utf8'), False)
            elif reply['type'] == 'websocket.close':
                self.sendClose(reply.get('code', 1000))

            self.resetTimeout()

    def onMessage(self, payload, isBinary):
        if not self.accepted:
            defer.returnValue(None)

        self.resetTimeout()

        if isBinary:
            self.queue.put_nowait({'type': 'websocket.receive', 'bytes': payload})
        else:
            self.queue.put_nowait({'type': 'websocket.receive', 'text': payload.decode('utf8')})

    def onClose(self, wasClean, code, reason):
        if not self.opened:
            return

        logger.info('Called onClose')

        self.queue.put_nowait({'type': 'websocket.disconnect', 'code': code})

    def timeoutConnection(self):
        logger.debug('Timeout from mixin')
        self.reply_defer.errback(defer.TimeoutError())

    def handle_reply(self, msg):
        d = self.reply_defer
        self.reply_defer = defer.Deferred()
        d.callback(msg)

    def do_cleanup(self):
        return self.factory.application.finish_protocol(self)


class ASGIWebSocketServerFactory(WebSocketServerFactory):
    protocol = ASGIWebSocketServerProtocol

    def __init__(self, *args, **kwargs):
        self.application = kwargs.pop('application')
        self.base_scope = kwargs.pop('base_scope')
        self.idle_timeout = kwargs.pop('idle_timeout')

        WebSocketServerFactory.__init__(self, *args, **kwargs)
