from autobahn.twisted.websocket import ConnectionDeny
from twisted.internet import defer, task
from twisted.trial.unittest import TestCase

from ..ws import ASGIWebSocketServerFactory, ASGIWebSocketServerProtocol
from .utils import DummyApplication


class DummyASGIWebSocketServerProtocol(ASGIWebSocketServerProtocol):
    clock = None

    def __init__(self, *args, **kwargs):
        self._events = []

        ASGIWebSocketServerProtocol.__init__(self, *args, **kwargs)

    def sendClose(self, code=None, reason=None):
        self._events.append(('send_close', code))

    def sendMessage(self, payload, isBinary=False, fragmentSize=None, sync=False, doNotCompress=False):
        self._events.append(('send_message', payload, isBinary))

    def dropConnection(self, abort=False):
        self._events.append(('drop_connection', abort))

    def callLater(self, timeout, func, *args, **kwargs):
        return self.clock.callLater(timeout, func, *args, **kwargs)


class DummyASGIWebSocketServerFactory(ASGIWebSocketServerFactory):
    protocol = DummyASGIWebSocketServerProtocol


class TestASGIWebSocket(TestCase):
    dummy_application = None

    def setUp(self):
        self.application = DummyApplication()
        self.base_scope = {'_ssl': ''}
        self.factory = DummyASGIWebSocketServerFactory(application=self.application,
                                                       base_scope=self.base_scope,
                                                       idle_timeout=600)

        self.clock = task.Clock()
        self.protocol = self.factory.buildProtocol(None)
        self.protocol.clock = self.clock

    @defer.inlineCallbacks
    def test_normal(self):
        self.assertFalse(self.protocol.opened)
        accept_defer = self.protocol.onConnect(None)
        self.assertEqual(self.application.scope, {'type': 'websocket', 'scheme': 'ws'})
        self.assertTrue(self.protocol.opened)
        self.assertFalse(accept_defer.called)

        reply = self.application.queue.get_nowait()
        self.assertEqual({'type': 'websocket.connect'}, reply)
        self.assertFalse(self.protocol.accepted)
        self.protocol.handle_reply({'type': 'websocket.accept'})
        yield accept_defer
        self.assertTrue(self.protocol.accepted)

        self.protocol.handle_reply({'type': 'websocket.send', 'binary': b'some binary stuff'})
        self.assertEqual(self.protocol._events.pop(), ('send_message', b'some binary stuff', True))

        self.protocol.handle_reply({'type': 'websocket.send', 'text': 'some text stuff'})
        self.assertEqual(self.protocol._events.pop(), ('send_message', b'some text stuff', False))

        self.protocol.onMessage(b'test binary', True)
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'websocket.receive', 'bytes': b'test binary'})

        self.protocol.onMessage(b'test text', False)
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'websocket.receive', 'text': 'test text'})

        self.protocol.handle_reply({'type': 'websocket.close'})
        self.assertEqual(self.protocol._events.pop(), ('send_close', 1000))

    @defer.inlineCallbacks
    def test_application_create_failed(self):
        self.application.fail_to_create = True
        accept_defer = self.protocol.onConnect(None)
        self.assertEqual(self.protocol._events.pop(), ('drop_connection', True))
        try:
            yield accept_defer
        except ConnectionDeny as e:
            self.assertEqual(e.code, 403)
        else:
            self.fail('Did not raise an exception')

    @defer.inlineCallbacks
    def test_connection_refused(self):
        accept_defer = self.protocol.onConnect(None)
        self.protocol.handle_reply({'type': 'websocket.close'})
        try:
            yield accept_defer
        except ConnectionDeny as e:
            self.assertEqual(e.code, 403)
        else:
            self.fail('Did not raise an exception')

    def test_timeout(self):
        self.protocol.onConnect(None)
        self.protocol.timeoutConnection()
        self.assertEqual(self.protocol._events.pop(), ('drop_connection', True))

    def test_cancel_defer(self):
        self.protocol.onConnect(None)
        self.protocol.reply_defer.cancel()
        self.assertEqual(self.protocol._events.pop(), ('drop_connection', True))

    def test_invalid_message_order(self):
        self.protocol.onConnect(None)
        self.protocol.handle_reply({'type': 'websocket.send', 'text': 'some text stuff'})
        self.assertEqual(len(self.protocol._events), 0)
        self.protocol.reply_defer.cancel()

    def test_connection_lost(self):
        self.protocol.onConnect(None)
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'websocket.connect'})
        self.protocol.onClose(True, 1000, '')
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'websocket.disconnect', 'code': 1000})
        self.protocol.reply_defer.cancel()

    def test_connection_lost_never_opened(self):
        self.protocol.onClose(True, 1000, '')
