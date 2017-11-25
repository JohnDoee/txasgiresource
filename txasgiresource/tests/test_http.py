from __future__ import unicode_literals

import os
import shutil
import tempfile

from asgiref.inmemory import ChannelLayer
from twisted.internet import defer
from twisted.python import failure
from twisted.trial.unittest import TestCase

from .. import http as asgihttp
from ..http import ASGIHTTPResource
from ..manager import ChannelLayerManager
from ..utils import sleep
from .utils import DummyRequest


class TestASGIHTTPResource(TestCase):
    def setUp(self):
        asgihttp.MAXIMUM_CONTENT_SIZE = 1000

        self.channel_layer = ChannelLayer()
        self.manager = ChannelLayerManager(self.channel_layer)
        self.temp_path = tempfile.mkdtemp()
        self._prepare_request()

    def _prepare_request(self):
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

        self.request = DummyRequest([b'test', b'path'])
        self.request.uri = b'http://dummy/test/path?a=b'

        self.resource = ASGIHTTPResource(self.manager, self.channel_base_payload, 1, use_x_sendfile=True)
        self.request_finished_defer = self.request.notifyFinish()

    @defer.inlineCallbacks
    def tearDown(self):
        shutil.rmtree(self.temp_path)
        yield self.manager.stop()

    def test_http_request(self):
        self.channel_base_payload['_ssl'] = 's'
        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.assertTrue(message['reply_channel'].startswith('txasgi.response'))
        self.assertEqual(message['http_version'], '1.0')
        self.assertEqual(message['method'], 'GET')
        self.assertEqual(message['scheme'], 'https')
        self.assertEqual(message['path'], '/test/path')
        self.assertEqual(message['query_string'], b'a=b')
        self.assertEqual(message['root_path'], '')
        self.assertListEqual(message['headers'], [[b'host', b'example.com'],
                                                  [b'user-agent', b'hack attack 1.0']])
        self.assertEqual(message.get('body_channel', None), None)
        self.assertEqual(message.get('body', b''), b'')

    @defer.inlineCallbacks
    def test_http_reply(self):
        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.channel_layer.send(message['reply_channel'], {
            'status': 200,
            'headers': [[b'server', b'my server software'],
                        [b'x-isgood', b'yes'],
                        [b'x-isgood', b'no']],
            'content': b'this is the result',
        })
        yield self.request_finished_defer

        expected_headers = [
            (b'X-Isgood', [b'yes', b'no']),
            (b'Server', [b'my server software']),
        ]

        for header in list(self.request.responseHeaders.getAllRawHeaders()):
            expected_headers.remove(header)

        self.assertEqual(expected_headers, [])

        self.assertEqual(self.request.written[0], b'this is the result')
        self.assertEqual(self.request.responseCode, 200)

    @defer.inlineCallbacks
    def test_http_reply_chunked_body(self):
        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.channel_layer.send(message['reply_channel'], {
            'status': 200,
            'headers': [[b'server', b'my server software'],
                        [b'x-isgood', b'yes']],
            'content': b'this is the result',
            'more_content': True,
        })

        self.channel_layer.send(message['reply_channel'], {
            'content': b'Better second',
        })

        yield self.request_finished_defer

        self.assertEqual(self.request.written[0], b'this is the result')
        self.assertEqual(self.request.written[1], b'Better second')

    @defer.inlineCallbacks
    def test_http_reply_timeout(self):
        self.resource.render(self.request)
        yield sleep(1.1)[0]

        yield self.request_finished_defer

        self.assertIn(b'Timeout', self.request.written[0])
        self.assertEqual(self.request.responseCode, 504)

    def test_http_request_body(self):
        body = os.urandom(asgihttp.MAXIMUM_CONTENT_SIZE - 1)
        self.request.content.write(body)
        self.request.content.seek(0, 0)

        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])
        self.assertEqual(message.get('body_channel'), None)
        self.assertEqual(message['body'], body)

    def test_http_request_more_content(self):
        body = os.urandom(asgihttp.MAXIMUM_CONTENT_SIZE * 2 + 50)
        self.request.content.write(body)
        self.request.content.seek(0, 0)

        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])
        body_channel = message['body_channel']
        self.assertTrue(body_channel.startswith('http.request.body?'))
        self.assertEqual(message['body'], body[:asgihttp.MAXIMUM_CONTENT_SIZE])

        _, message = self.channel_layer.receive([body_channel])
        self.assertEqual(message['content'], body[asgihttp.MAXIMUM_CONTENT_SIZE:asgihttp.MAXIMUM_CONTENT_SIZE * 2])
        self.assertEqual(message['more_content'], True)

        _, message = self.channel_layer.receive([body_channel])
        self.assertEqual(message['content'], body[asgihttp.MAXIMUM_CONTENT_SIZE * 2:])
        self.assertEqual(message['more_content'], False)

    @defer.inlineCallbacks
    def test_http_request_channel_full(self):
        self.channel_layer.capacity = 0
        self.resource.render(self.request)

        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 503)
        self.assertIn(b'Channel is full,', self.request.written[0])

    @defer.inlineCallbacks
    def test_http_request_connection_lost(self):
        self.resource.render(self.request)
        self.request.processingFailed(failure.Failure(Exception()))

        try:
            yield self.request_finished_defer
        except:
            pass

        _, request_message = self.channel_layer.receive(['http.request'])
        _, disconnect_message = self.channel_layer.receive(['http.disconnect'])
        self.assertEqual(request_message['reply_channel'], disconnect_message['reply_channel'])
        self.assertEqual(request_message['path'], disconnect_message['path'])
        self.assertEqual(disconnect_message['path'], self.channel_base_payload['path'])

    @defer.inlineCallbacks
    def test_http_request_connection_lost_chunked(self):
        original_chunk_sleep_delay = asgihttp.CHUNK_SLEEP_DELAY
        asgihttp.CHUNK_SLEEP_DELAY = 0.4

        body = os.urandom(asgihttp.MAXIMUM_CONTENT_SIZE * 2 + 50)
        self.request.content.write(body)
        self.request.content.seek(0, 0)

        self.channel_layer.capacity = 1
        self.resource.render(self.request)

        yield sleep(0.1)[0]

        self.request.processingFailed(failure.Failure(Exception()))

        try:
            yield self.request_finished_defer
        except:
            pass

        self.channel_layer.capacity = 100

        yield sleep(0.5)[0]

        _, message = self.channel_layer.receive(['http.request'])
        body_channel = message['body_channel']

        channel, message = self.channel_layer.receive([body_channel])
        _, message = self.channel_layer.receive([body_channel])
        self.assertEqual(message['closed'], True)

        asgihttp.CHUNK_SLEEP_DELAY = original_chunk_sleep_delay

    @defer.inlineCallbacks
    def test_http_request_channel_full_chunked(self):
        body = os.urandom(asgihttp.MAXIMUM_CONTENT_SIZE * 2 + 50)
        self.request.content.write(body)
        self.request.content.seek(0, 0)

        self.channel_layer.capacity = 1
        self.resource.render(self.request)
        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 503)
        self.assertIn(b'Channel is full while sending chunks', self.request.written[0])

    @defer.inlineCallbacks
    def test_http_request_sendfile(self):
        temp_file = os.path.join(self.temp_path, 'tempfile')
        file_payload = b'a' * 50
        with open(temp_file, 'wb') as f:
            f.write(file_payload)

        # normal request
        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.channel_layer.send(message['reply_channel'], {
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
            'content': b'',
        })
        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 200)
        self.assertEqual(self.request.written[0], file_payload)

        # cached request
        etag = self.request.responseHeaders.getRawHeaders('etag')

        self._prepare_request()
        self.request.requestHeaders.addRawHeader(b'if-none-match', etag[0])

        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.channel_layer.send(message['reply_channel'], {
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
            'content': b'',
        })
        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 304)
        self.assertEqual(self.request.written[0], b'')

        # file gone request
        self._prepare_request()
        os.remove(temp_file)

        self.resource.render(self.request)

        _, message = self.channel_layer.receive(['http.request'])

        self.channel_layer.send(message['reply_channel'], {
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
            'content': b'',
        })
        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 404)
