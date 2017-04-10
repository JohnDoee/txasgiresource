from __future__ import unicode_literals

import logging

from asgiref.inmemory import ChannelLayer
from twisted.internet import defer, task
from twisted.trial.unittest import TestCase

from .. import ws as asgiws
from ..manager import ChannelLayerManager
from ..utils import sleep
from ..ws import ASGIWebSocketServerFactory, ASGIWebSocketServerProtocol

logger = logging.getLogger(__name__)


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
    def setUp(self):
        self.channel_layer = ChannelLayer()
        self.manager = ChannelLayerManager(self.channel_layer)
        self.channel_base_payload = {
            'path': '/test/path',
            'query_string': b'a=b',
            'root_path': '',
            'headers': [[b'host', b'example.com'],
                        [b'user-agent', b'hack attack 1.0']],
            'client': ['127.0.0.1', 5000],
            'server': ['127.0.0.1', 80],
            '_ssl': '',
        }
        self.factory = DummyASGIWebSocketServerFactory(manager=self.manager,
                                                       channel_base_payload=self.channel_base_payload,
                                                       idle_timeout=600)

        self.clock = task.Clock()
        self.protocol = self.factory.buildProtocol(None)
        self.protocol.clock = self.clock

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.manager.stop()

    @defer.inlineCallbacks
    def test_ws_normal_session(self):
        self.protocol.onConnect(None)
        self.protocol.accepted = True

        _, message = self.channel_layer.receive(['websocket.connect'])
        self.assertEqual(message.get('scheme', 'ws'), 'ws')
        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertTrue('!' in message['reply_channel'])
        self.assertEqual(message['order'], 0)

        reply_channel = message['reply_channel']

        for i in range(1, 4):
            msg = b'happy hiphopopotamusses'
            self.protocol.onMessage(msg, False)

            _, message = self.channel_layer.receive(['websocket.receive'])
            logger.debug('Doing loop %s' % (i, ))

            self.assertEqual(message.get('bytes'), None)
            self.assertEqual(message.get('text'), msg.decode('utf8'))

            self.assertEqual(message['order'], i)
            self.assertEqual(message['path'], self.channel_base_payload['path'])
            self.assertEqual(message['reply_channel'], reply_channel)

        msg = b'angry rhymenocerous'
        self.protocol.onMessage(msg, True)

        _, message = self.channel_layer.receive(['websocket.receive'])

        self.assertEqual(message.get('text'), None)
        self.assertEqual(message.get('bytes'), msg)

        self.assertEqual(message['order'], 4)
        self.assertEqual(message['path'], self.channel_base_payload['path'])
        self.assertEqual(message['reply_channel'], reply_channel)

        for i in range(4):
            self.channel_layer.send(reply_channel, {'text': 'message %i' % (i, )})

        self.channel_layer.send(reply_channel, {'binary': b'message', 'close': True})

        yield sleep(0.1)[0]

        for i in range(4):
            event = self.protocol._events.pop(0)
            self.assertEqual(event[0], 'send_message')
            self.assertEqual(event[1], ('message %i' % (i, )).encode('utf8'))
            self.assertEqual(event[2], False)

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'send_message')
        self.assertEqual(event[1], b'message')
        self.assertEqual(event[2], True)

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'send_close')

        self.protocol.onClose(True, 1013, '')

        _, message = self.channel_layer.receive(['websocket.disconnect'])
        self.assertEqual(message['reply_channel'], reply_channel)
        self.assertEqual(message['code'], 1013)
        self.assertEqual(message['path'], self.channel_base_payload['path'])
        self.assertEqual(message['order'], 5)

    def test_ws_timeout(self):
        self.protocol.onConnect(None)
        self.protocol.accepted = True

        _, message = self.channel_layer.receive(['websocket.connect'])
        self.assertEqual(message.get('scheme', 'ws'), 'ws')
        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertTrue('!' in message['reply_channel'])
        self.assertEqual(message['order'], 0)

        self.protocol.clock.pump([800])

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'drop_connection')

    @defer.inlineCallbacks
    def test_ws_channel_timeout(self):
        self.factory.idle_timeout = 0.2

        self.protocol.onConnect(None)
        self.protocol.accepted = True

        _, message = self.channel_layer.receive(['websocket.connect'])
        self.assertEqual(message.get('scheme', 'ws'), 'ws')
        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertTrue('!' in message['reply_channel'])
        self.assertEqual(message['order'], 0)

        yield sleep(0.4)[0]

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'drop_connection')

    def test_ws_channel_full(self):
        self.channel_layer.capacity = 0

        self.protocol.onConnect(None)
        self.protocol.accepted = True

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'send_close')
        self.assertEqual(event[1], 1013)

    @defer.inlineCallbacks
    def test_ws_channel_full_retry(self):
        original_send_channel_sleep_delay = asgiws.SEND_CHANNEL_SLEEP_DELAY
        asgiws.SEND_CHANNEL_SLEEP_DELAY = 0.1

        self.protocol.onConnect(None)
        self.protocol.accepted = True

        self.channel_layer.capacity = 0

        self.protocol.onMessage(b'happy hiphopopotamusses', False)
        yield sleep(0.2)[0]
        self.assertEqual(len(self.protocol._events), 0)

        yield sleep(0.5)[0]
        self.assertEqual(len(self.protocol._events), 1)

        event = self.protocol._events.pop(0)
        self.assertEqual(event[0], 'send_close')
        self.assertEqual(event[1], 1013)

        asgiws.SEND_CHANNEL_SLEEP_DELAY = original_send_channel_sleep_delay

    @defer.inlineCallbacks
    def test_ws_channel_full_retry_success(self):
        original_send_channel_sleep_delay = asgiws.SEND_CHANNEL_SLEEP_DELAY
        asgiws.SEND_CHANNEL_SLEEP_DELAY = 0.1

        self.protocol.onConnect(None)
        self.protocol.accepted = True

        self.channel_layer.capacity = 0

        msg = b'happy hiphopopotamusses'
        self.protocol.onMessage(msg, True)
        yield sleep(0.2)[0]
        self.assertEqual(len(self.protocol._events), 0)

        self.channel_layer.capacity = 100

        yield sleep(0.5)[0]
        self.assertEqual(len(self.protocol._events), 0)

        _, message = self.channel_layer.receive(['websocket.receive'])

        self.assertEqual(message.get('bytes'), msg)

        asgiws.SEND_CHANNEL_SLEEP_DELAY = original_send_channel_sleep_delay

    @defer.inlineCallbacks
    def test_ws_request_accept(self):
        self.protocol.onConnect(None)

        _, message = self.channel_layer.receive(['websocket.connect'])
        self.assertEqual(message.get('scheme', 'ws'), 'ws')
        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertTrue('!' in message['reply_channel'])
        self.assertEqual(message['order'], 0)

        reply_channel = message['reply_channel']

        msg = b'happy hiphopopotamusses'
        self.protocol.onMessage(msg, False)
        _, message = self.channel_layer.receive(['websocket.receive'])
        self.assertEqual(message, None)

        self.channel_layer.send(reply_channel, {'accept': True})

        yield sleep(0.2)[0]

        self.protocol.onMessage(msg, False)
        _, message = self.channel_layer.receive(['websocket.receive'])
        self.assertNotEqual(message, None)

    @defer.inlineCallbacks
    def test_ws_request_accept_rejected(self):
        self.protocol.onConnect(None)

        _, message = self.channel_layer.receive(['websocket.connect'])
        self.assertEqual(message.get('scheme', 'ws'), 'ws')
        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertTrue('!' in message['reply_channel'])
        self.assertEqual(message['order'], 0)

        reply_channel = message['reply_channel']

        msg = b'happy hiphopopotamusses'
        self.protocol.onMessage(msg, False)
        _, message = self.channel_layer.receive(['websocket.receive'])
        self.assertEqual(message, None)

        self.channel_layer.send(reply_channel, {'accept': False})

        yield sleep(0.2)[0]

        self.protocol.onMessage(msg, False)
        _, message = self.channel_layer.receive(['websocket.receive'])
        self.assertEqual(message, None)
