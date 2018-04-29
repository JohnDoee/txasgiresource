import hashlib
import logging
import os

from twisted.internet import defer, reactor
from twisted.web import http, resource, server, static

from .utils import send_error_page

logger = logging.getLogger(__name__)

MAXIMUM_CONTENT_SIZE = 950 * 1024


class ASGIHTTPResource(resource.Resource):
    isLeaf = True
    request = None

    def __init__(self, application, base_scope, timeout=None, use_x_sendfile=False):
        self.application = application
        self.base_scope = base_scope
        self.timeout = timeout
        self.use_x_sendfile = use_x_sendfile
        self.reply_defer = defer.Deferred()

        resource.Resource.__init__(self)

    def send_request_to_application(self, request, content):
        # get size to figure out if we need to chunk request
        content.seek(0, os.SEEK_END)
        content_size = content.tell()
        content.seek(0, 0)

        logger.debug('Sending initial HTTP request')
        while True:
            body = content.read(MAXIMUM_CONTENT_SIZE)
            more_body = content.tell() < content_size

            self.queue.put_nowait({
                'type': 'http.request',
                'body': body,
                'more_body': more_body,
            })

            if not more_body:
                break

        self.wait_for_application_reply(request)

    @defer.inlineCallbacks
    def wait_for_application_reply(self, request):
        def connection_lost(failure):
            failure.trap(Exception)
            request.finished = 1
            self.queue.put_nowait({'type': 'http.disconnect'})
            self.do_cleanup(is_finished=True)
        request.notifyFinish().addErrback(connection_lost)

        did_x_sendfile = False
        sent_header = False
        while True:
            try:
                self.reply_defer.addTimeout(self.timeout, reactor)
                reply = yield self.reply_defer
            except defer.TimeoutError:
                logger.debug('We hit a timeout')
                send_error_page(request, 504, 'Timeout while waiting for upstream',
                                'Timeout while waiting for upstream')
                defer.returnValue(None)
            except defer.CancelledError:
                send_error_page(request, 503, 'Request cancelled',
                                'Request was cancelled by server before it finished processing')
                defer.returnValue(None)

            if reply['type'] == 'http.response.start':
                if sent_header:
                    raise ValueError('Headers already sent')

                x_sendfile_path = None
                for name, value in reply['headers']:
                    if self.use_x_sendfile and name.lower() == b'x-sendfile':
                        x_sendfile_path = value
                    else:
                        request.responseHeaders.addRawHeader(name, value)

                if x_sendfile_path:
                    logger.debug('We got a request for sendfile at %s' % (x_sendfile_path, ))
                    did_x_sendfile = True
                    yield self.do_sendfile(request, x_sendfile_path)
                else:
                    request.setResponseCode(reply['status'])

                sent_header = True
                continue

            elif reply['type'] == 'http.response.body':
                if not sent_header:
                    pass

                if not request.finished and request.channel is not None:
                    request.write(not did_x_sendfile and reply.get('body', b'') or b'')

                if not reply.get('more_body', False) or request.finished or not request.channel:
                    break

        if not request.finished:
            request.finish()

        self.do_cleanup()

    def handle_reply(self, msg):
        d = self.reply_defer
        self.reply_defer = defer.Deferred()
        d.callback(msg)

    @defer.inlineCallbacks
    def _render(self, request):
        self.request = request

        scope = dict(self.base_scope)
        scope['type'] = 'http'
        scope['http_version'] = request.clientproto.decode('utf8').split('/')[1]
        scope['scheme'] = 'http%s' % (scope.pop('_ssl'))
        scope['method'] = request.method.decode('utf8')

        self.queue = yield self.application.create_application_instance(self, scope)

        self.send_request_to_application(request, request.content)

    def render(self, request):
        self._render(request)

        return server.NOT_DONE_YET

    @defer.inlineCallbacks
    def do_sendfile(self, request, path):
        if not os.path.isfile(path):
            request.setResponseCode(404)
            defer.returnValue(None)

        etag = hashlib.sha1(path).hexdigest()[:16].encode('ascii')
        if request.setETag(etag) != http.CACHED:
            finished_defer = request.notifyFinish()
            static.File(path).render(request)
            yield finished_defer

    def do_cleanup(self, is_finished=False):
        logger.debug('Cleaning up after finished request')

        if not is_finished and self.request and not self.request.finished:
            self.request.finish()

        if self.reply_defer and not self.reply_defer.called and self.reply_defer.callbacks:
            self.reply_defer.cancel()

        return self.application.finish_protocol(self)
