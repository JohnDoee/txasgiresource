import os
import shutil
import tempfile

from twisted.internet import defer
from twisted.python import failure
from twisted.trial.unittest import TestCase

from .. import http as asgihttp
from ..http import ASGIHTTPResource
from ..utils import sleep
from .utils import DummyApplication, DummyRequest


class TestASGIHTTP(TestCase):
    def setUp(self):
        self.application = DummyApplication()
        self.base_scope = {'_ssl': ''}
        self._prepare_request()
        self.temp_path = tempfile.mkdtemp()

    def _prepare_request(self):
        self.request = DummyRequest([b'test', b'path'])
        self.request.uri = b'http://dummy/test/path?a=b'
        self.request_finished_defer = self.request.notifyFinish()
        self.resource = ASGIHTTPResource(self.application, self.base_scope, 1, use_x_sendfile=True)

    def tearDown(self):
        shutil.rmtree(self.temp_path)

    @defer.inlineCallbacks
    def test_normal_http_request(self):
        self.resource.render(self.request)
        self.assertEqual(self.application.scope, {'type': 'http', 'scheme': 'http', 'http_version': '1.0', 'method': 'GET'})
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.request', 'body': b'', 'more_body': False})
        self.resource.handle_reply({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'server', b'my server software'],
                        [b'x-isgood', b'yes'],
                        [b'x-isgood', b'no']],
        })
        self.resource.handle_reply({'type': 'http.response.body', 'body': b'this is the result'})
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
    def test_timeout(self):
        self.resource.render(self.request)
        yield sleep(1.1)[0]

        yield self.request_finished_defer

        self.assertIn(b'Timeout', self.request.written[0])
        self.assertEqual(self.request.responseCode, 504)

    @defer.inlineCallbacks
    def test_cancel_defer(self):
        self.resource.render(self.request)
        self.resource.reply_defer.cancel()

        yield self.request_finished_defer

        self.assertIn(b'cancelled', self.request.written[0])
        self.assertEqual(self.request.responseCode, 503)

    @defer.inlineCallbacks
    def test_http_reply_chunked_body(self):
        body = os.urandom(asgihttp.MAXIMUM_CONTENT_SIZE * 2 + 50)
        self.request.content.write(body)
        self.request.content.seek(0, 0)

        self.resource.render(self.request)

        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.request', 'body': body[:asgihttp.MAXIMUM_CONTENT_SIZE], 'more_body': True})
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.request', 'body': body[asgihttp.MAXIMUM_CONTENT_SIZE:asgihttp.MAXIMUM_CONTENT_SIZE * 2], 'more_body': True})
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.request', 'body': body[asgihttp.MAXIMUM_CONTENT_SIZE * 2:], 'more_body': False})

        self.resource.reply_defer.cancel()
        try:
            yield self.request_finished_defer
        except:
            pass

    @defer.inlineCallbacks
    def test_http_request_connection_lost(self):
        self.resource.render(self.request)
        self.request.processingFailed(failure.Failure(Exception()))

        try:
            yield self.request_finished_defer
        except:
            pass
        else:
            self.fail('Should raise an exception')

        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.request', 'body': b'', 'more_body': False})
        self.assertEqual(self.application.queue.get_nowait(), {'type': 'http.disconnect'})

    @defer.inlineCallbacks
    def test_http_request_sendfile(self):
        temp_file = os.path.join(self.temp_path, 'tempfile')
        file_payload = b'a' * 50
        with open(temp_file, 'wb') as f:
            f.write(file_payload)

        # normal request
        self.resource.render(self.request)

        self.resource.handle_reply({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
        })
        self.resource.handle_reply({'type': 'http.response.body', 'body': b''})

        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 200)
        self.assertEqual(self.request.written[0], file_payload)

        # cached request
        etag = self.request.responseHeaders.getRawHeaders('etag')

        self._prepare_request()
        self.request.requestHeaders.addRawHeader(b'if-none-match', etag[0])

        self.resource.render(self.request)

        self.resource.handle_reply({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
        })
        self.resource.handle_reply({'type': 'http.response.body', 'body': b''})

        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 304)
        self.assertEqual(self.request.written[0], b'')

        # file gone request
        self._prepare_request()
        os.remove(temp_file)

        self.resource.render(self.request)

        self.resource.handle_reply({
            'type': 'http.response.start',
            'status': 200,
            'headers': [[b'x-sendfile', temp_file.encode('utf-8')]],
        })
        self.resource.handle_reply({'type': 'http.response.body', 'body': b''})
        yield self.request_finished_defer

        self.assertEqual(self.request.responseCode, 404)
