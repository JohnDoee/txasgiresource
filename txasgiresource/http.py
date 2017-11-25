from __future__ import unicode_literals

import hashlib
import logging
import os

from twisted.internet import defer
from twisted.web import http, resource, server, static

from .utils import send_error_page, sleep

logger = logging.getLogger(__name__)

MAXIMUM_CONTENT_SIZE = 950 * 1024
CHUNK_SLEEP_DELAY = 0.05
CHUNK_RETRY_COUNT = 3


class ASGIHTTPResource(resource.Resource):
    isLeaf = True

    def __init__(self, manager, channel_base_payload, timeout=None, use_x_sendfile=False):
        self.manager = manager
        self.channel_base_payload = channel_base_payload
        self.timeout = timeout
        self.use_x_sendfile = True

        resource.Resource.__init__(self)

    @defer.inlineCallbacks
    def send_channel_layer_request(self, request, channel_payload, content):
        # get size to figure out if we need to chunk request
        content.seek(0, os.SEEK_END)
        content_size = content.tell()
        content.seek(0, 0)

        # setup channel
        channel = self.manager.get_channel(self.timeout)
        channel_payload['reply_channel'] = channel.reply_channel

        if content_size > 0:
            request_body_chunk_channel = self.manager.new_channel('http.request.body?')

            channel_payload['body'] = content.read(MAXIMUM_CONTENT_SIZE)
            if content.tell() < content_size:
                channel_payload['body_channel'] = request_body_chunk_channel
                logger.info('We have more body')

        # do the first send
        try:
            logger.debug('Sending initial http.request: %r' % (channel_payload, ))
            channel.send('http.request', channel_payload)
        except self.manager.ChannelFull:
            logger.warning('We hit a full channel')

            send_error_page(request, 503, 'Channel is full', 'Channel is full, please try again later')
            defer.returnValue(None)

        # send more chunks, if there's any data
        if content.tell() < content_size:
            logger.debug('The body is not completely sent')
            # setup for connection lost situation
            chunk_status = {
                'finished_with_chunks': False,
                'connection_lost': False,
                'informed_connection_lost': False
            }

            def connection_lost(failure):
                failure.trap(Exception)
                if chunk_status['finished_with_chunks']:
                    return

                logger.warning('We lost connection while sending chunks')
                chunk_status['connection_lost'] = True
            request.notifyFinish().addErrback(connection_lost)

            while content.tell() < content_size:
                for i in range(1, CHUNK_RETRY_COUNT + 1):  # retry counter, used to extend sleep times
                    if chunk_status['connection_lost']:
                        chunk_channel_payload = {
                            'closed': True,
                        }
                        chunk_status['informed_connection_lost'] = True
                    else:
                        chunk_channel_payload = {
                            'content': content.read(MAXIMUM_CONTENT_SIZE),
                        }
                        chunk_channel_payload['more_content'] = content.tell() < content_size

                    try:
                        channel.send(request_body_chunk_channel, chunk_channel_payload)
                        break
                    except self.manager.ChannelFull:
                        logger.debug('We hit a full channel while chunking')
                        yield sleep(CHUNK_SLEEP_DELAY * i)[0]
                else:  # chunk was not sent successfully
                    if not chunk_status['connection_lost']:
                        logger.warning('Unable to send the chunk because channel was full, aborting request')
                        send_error_page(request, 503, 'Channel is full',
                                        'Channel is full while sending chunks, please try again later')

                        defer.returnValue(None)

                if chunk_status['connection_lost'] and chunk_status['informed_connection_lost']:
                    defer.returnValue(None)

            chunk_status['finished_with_chunks'] = True

        self.get_channel_layer_reply(channel, request, channel_payload['path'])

    @defer.inlineCallbacks
    def get_channel_layer_reply(self, channel, request, path):
        logger.debug('Waiting for reply on %s' % (channel.reply_channel, ))

        def connection_lost(failure):
            failure.trap(Exception)

            channel.send('http.disconnect', {
                'reply_channel': channel.reply_channel,
                'path': path,
            })
            channel.finished()
        request.notifyFinish().addErrback(connection_lost)

        sent_header = False
        while True:
            try:
                reply = yield channel.get_reply()
            except self.manager.Timeout:
                logger.debug('We hit a timeout')
                send_error_page(request, 504, 'Timeout while waiting for upstream',
                                'Timeout while waiting for upstream')
                defer.returnValue(None)
            except defer.CancelledError:
                send_error_page(request, 503, 'Request cancelled',
                                'Request was cancelled by server before it finished processing')
                defer.returnValue(None)

            if not sent_header:
                x_sendfile_path = None
                for name, value in reply['headers']:
                    if self.use_x_sendfile and name.lower() == b'x-sendfile':
                        x_sendfile_path = value
                    else:
                        request.responseHeaders.addRawHeader(name, value)

                if x_sendfile_path:
                    logger.debug('We got a request for sendfile at %s' % (x_sendfile_path, ))
                    yield self.do_sendfile(request, x_sendfile_path)
                else:
                    request.setResponseCode(reply['status'])

                sent_header = True

            if not request.finished:
                request.write(reply.get('content', ''))

            if not reply.get('more_content', False) or request.finished:
                break

        channel.finished()
        if not request.finished:
            request.finish()

    def render(self, request):
        channel_payload = self.channel_base_payload

        channel_payload['http_version'] = request.clientproto.decode('utf8').split('/')[1]
        channel_payload['scheme'] = 'http%s' % (channel_payload.pop('_ssl'))
        channel_payload['method'] = request.method.decode('utf8')

        self.send_channel_layer_request(request, channel_payload, request.content)

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
