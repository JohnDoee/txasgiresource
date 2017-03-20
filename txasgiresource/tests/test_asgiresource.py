from __future__ import unicode_literals

from asgiref.inmemory import ChannelLayer
from twisted.internet import defer
from twisted.internet.address import IPv4Address, IPv6Address, UNIXAddress
from twisted.trial.unittest import TestCase

from ..asgiresource import ASGIResource
from .utils import DummyRequest


class ASGIResourceDummy(ASGIResource):
    def __init__(self, *args, **kwargs):
        self._dispatches = []

        ASGIResource.__init__(self, *args, **kwargs)

    def dispatch_websocket(self, request, channel_base_payload):
        self._dispatches.append(('websocket', request, channel_base_payload))

    def dispatch_http(self, request, channel_base_payload):
        self._dispatches.append(('http', request, channel_base_payload))


class TestASGIResource(TestCase):
    def setUp(self):
        self.channel_layer = ChannelLayer()
        self.resource = ASGIResourceDummy(channel_layer=self.channel_layer, root_path='')

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.resource.manager.stop()

    def test_http_request(self):
        request = DummyRequest([b'test', b'path'])
        request.client = IPv4Address("TCP", "127.0.0.1", 5000)
        request.host = IPv4Address("TCP", "127.0.0.1", 80)
        request.requestHeaders.addRawHeader(b'host', b'example.com')

        request.uri = b'http://dummy/test/path?a=b'
        self.resource.render(request)

        self.assertEqual(len(self.resource._dispatches), 1)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertEqual(dispatcher, 'http')
        self.assertEqual(channel_base_payload['_ssl'], '')
        self.assertEqual(channel_base_payload['path'], '/test/path')
        self.assertEqual(channel_base_payload['query_string'], b'a=b')
        self.assertEqual(channel_base_payload['root_path'], '')
        self.assertListEqual(channel_base_payload['headers'], [[b'host', b'example.com']])
        self.assertListEqual(channel_base_payload['client'], ['127.0.0.1', 5000])
        self.assertListEqual(channel_base_payload['server'], ['127.0.0.1', 80])

    def test_http_request_encoding(self):
        request = DummyRequest([b'test', b'\xc3\xa6\xc3\xb8\xc3\xa5', b''])
        request.uri = b'http://dummy/test/%C3%A6%C3%B8%C3%A5/?test=%C3%A6%C3%B8%C3%A5'

        self.resource.render(request)

        self.assertEqual(len(self.resource._dispatches), 1)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertEqual(dispatcher, 'http')
        self.assertEqual(channel_base_payload['_ssl'], '')
        self.assertEqual(channel_base_payload['path'], '/test/\xe6\xf8\xe5/')
        self.assertEqual(channel_base_payload['query_string'], b'test=%C3%A6%C3%B8%C3%A5')
        self.assertEqual(channel_base_payload['root_path'], '')

    def test_websocket_request(self):
        request = DummyRequest([b'test', b'path'])
        request.requestHeaders.addRawHeader(b'upgrade', b'websocket')
        request.uri = b'https://dummy/test/path'
        request._isSecure = True

        self.resource.render(request)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertEqual(dispatcher, 'websocket')
        self.assertEqual(channel_base_payload['_ssl'], 's')

    def test_ipv6(self):
        request = DummyRequest([b'test', b'path'])
        request.client = IPv6Address('TCP', '::1', 5000)
        request.host = IPv6Address('TCP', '::1', 80)

        request.uri = b'http://dummy/test/path'
        self.resource.render(request)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertListEqual(channel_base_payload['client'], ['::1', 5000])
        self.assertListEqual(channel_base_payload['server'], ['::1', 80])

    def test_unixsocket(self):
        request = DummyRequest([b'test', b'path'])
        request.host = UNIXAddress(b'/home/test/sockets/server.sock')

        request.uri = b'http://dummy/test/path'
        request.requestHeaders.addRawHeader('X-Forwarded-For', '127.4.3.2')
        request.requestHeaders.addRawHeader('X-Forwarded-Port', '12312')
        self.resource.render(request)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertEqual(channel_base_payload['client'], None)
        self.assertEqual(channel_base_payload['server'], None)

    def test_use_proxy_headers(self):
        self.resource.use_proxy_headers = True

        request = DummyRequest([b'test', b'path'])
        request.requestHeaders.addRawHeader('X-Forwarded-For', '127.4.3.2')
        request.requestHeaders.addRawHeader('X-Forwarded-Port', '12312')
        request.host = UNIXAddress(b'/home/test/sockets/server.sock')

        request.uri = b'http://dummy/test/path'
        self.resource.render(request)

        dispatcher, _, channel_base_payload = self.resource._dispatches[0]
        self.assertEqual(channel_base_payload['client'], ['127.4.3.2', 12312])
        self.assertEqual(channel_base_payload['server'], None)
